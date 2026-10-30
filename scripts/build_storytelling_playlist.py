"""Build a deterministic offline playlist from an already reviewed collection.

No text, speech or ambient generation. Source WAVs/plans remain immutable.
Run: py -3.10 -m scripts.build_storytelling_playlist
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import wave
from pathlib import Path

from home_podcast.storytelling_quality import require_personal_story, validate_personal_visual_plan
from home_podcast.ambient_mastering import _spawn

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COLLECTION = Path('work/storytelling-real-december/rich-visuals-2026-10-29/collection.json')
WORK = Path('work/storytelling-real-december/playlist-35-2026-10-29')
AUDIO = Path('audio/storytelling-real-december/playlist-35-2026-10-29')
MODES = ('original', 'human_figures', 'balanced')
RATE = 48000


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def flatten(collection, mode):
    """Offset clocks only. Preserve every prompt, excerpt, cast and seed."""
    first = collection['stories'][0]['paths'][mode]['plan']
    plan = {k: copy.deepcopy(first[k]) for k in
            ('contract_version', 'touchdesigner_version', 'project_variant',
             'timing_policy', 'prompt_policy', 'grounding_policy')}
    plan.update(kind='reviewed_storytelling_playlist', episode_id=f'real-december-reviewed-{len(collection["stories"])}',
                duration_ms=0, master_track='voices_only', visual_path={'id': mode},
                loop_transition_policy='fade_to_black_no_prompt_preview',
                output_edge_fades={'default_ms': 1000, 'applies_at': 'each_story_and_full_loop'},
                sequencer_module='touchdesigner/storytelling_playlist_sequencer.py',
                playlist_stories=[], scenes=[], captions=[], editorial_review_required=True)
    offset = 0
    for row in collection['stories']:
        source = row['paths'][mode]['plan']
        if source['duration_ms'] != row['duration_ms']:
            raise ValueError('Visual and audio clocks differ')
        prefix = row['narration_id']+'--'
        boundary = {k: row[k] for k in ('number', 'narration_id', 'title', 'duration_ms')}
        boundary.update(start_ms=offset, end_ms=offset+row['duration_ms'],
                        source_visual=row['paths'][mode]['path'],
                        source_visual_sha256=row['paths'][mode]['sha256'])
        plan['playlist_stories'].append(boundary)
        for old in source['scenes']:
            scene = copy.deepcopy(old)
            scene['source_scene_id'] = old['scene_id']
            scene['scene_id'] = prefix+old['scene_id']
            scene['narration_id'] = row['narration_id']
            scene['sequence'] = len(plan['scenes'])+1
            for key in ('start_ms', 'end_ms'):
                scene[key] += offset
            scene['segment_ids'] = [prefix+s for s in scene.get('segment_ids', [])]
            if 'not_before_ms' in scene.get('speech_anchor', {}):
                scene['speech_anchor']['not_before_ms'] += offset
            for cue in scene.get('ambient_context', []):
                for key in ('start_ms', 'end_ms'):
                    cue[key] += offset
            if old['start_ms'] == 0:
                scene['crossfade_in_ms'] = 0
            plan['scenes'].append(scene)
        for old in source['captions']:
            caption = copy.deepcopy(old)
            caption['caption_id'] = prefix+old['caption_id']
            caption['narration_id'] = row['narration_id']
            caption['start_ms'] += offset
            caption['end_ms'] += offset
            plan['captions'].append(caption)
        offset += row['duration_ms']
    plan['duration_ms'] = offset
    return plan


def run_ffmpeg(ffmpeg, args):
    result = _spawn([str(ffmpeg), '-threads', '1', '-filter_threads', '1',
                     '-hide_banner', '-loglevel', 'error', '-y', *args])
    if result.returncode:
        raise RuntimeError(result.stderr[-2000:])


def wave_info(path):
    with wave.open(str(path), 'rb') as stream:
        return dict(channels=stream.getnchannels(), sample_width=stream.getsampwidth(),
                    sample_rate=stream.getframerate(), frames=stream.getnframes())


def concatenate(paths, output):
    temporary = output.with_suffix('.tmp.wav')
    with wave.open(str(temporary), 'wb') as destination:
        destination.setnchannels(2)
        destination.setsampwidth(2)
        destination.setframerate(RATE)
        for path in paths:
            with wave.open(str(path), 'rb') as source:
                if source.getparams()[:3] != (2, 2, RATE):
                    raise ValueError('Cached playlist segment has incompatible format')
                while block := source.readframes(RATE*10):
                    destination.writeframesraw(block)
    temporary.replace(output)


def build(root=ROOT, collection_path=DEFAULT_COLLECTION, ffmpeg=None, ambient_db=0.0,
          work_dir=WORK, audio_dir=AUDIO, reuse_segments_from=None):
    # Source soundscape_only is already a -30 LUFS bed, not the louder solo
    # audition master. Do not attenuate an approved background stem twice.
    if not -30 <= ambient_db <= 0:
        raise ValueError('Combined background gain must be between -30 and 0 dB')
    root = Path(root).resolve()
    # Explicit edition directories keep the saved .26/35-story show intact.
    work, output = (root/Path(p) for p in (work_dir, audio_dir))
    for path, parent in ((work, root/'work/storytelling-real-december'),
                         (output, root/'audio/storytelling-real-december')):
        if path.resolve() == parent.resolve() or not path.resolve().is_relative_to(parent.resolve()):
            raise ValueError('Playlist edition must be inside its dedicated project subtree')
    reuse = None
    if reuse_segments_from is not None:
        reuse = (root/Path(reuse_segments_from)).resolve()
        if not reuse.is_relative_to((root/'work/storytelling-real-december').resolve()) or reuse.name != 'segments':
            raise ValueError('Reuse only a project-local playlist segment cache')
    collection_file = root/collection_path
    collection = read(collection_file)
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    ffmpeg = ffmpeg or next((root/'work/storytelling-real-december/tools').glob('ffmpeg-*/**/bin/ffmpeg.exe'))
    protected = {str(collection_path): sha(collection_file)}
    # A source-bound review is required per story, never a synthetic collection approval.
    for row in collection['stories']:
        directory = root/'narrations/real-december'/row['narration_id']
        require_personal_story(directory)
        adaptation = read(directory/'adaptation.json')
        for name in ('adaptation.json', 'personal-story-review.json'):
            protected[(directory/name).relative_to(root).as_posix()] = sha(directory/name)
        for mode in MODES:
            entry = row['paths'][mode]
            path = root/entry['path']
            if sha(path) != entry['sha256'] or read(path) != entry['plan']:
                raise ValueError('Stale reviewed visual input')
            validate_personal_visual_plan(entry['plan'], adaptation)
            protected[entry['path']] = entry['sha256']
        for kind in ('voices_only', 'soundscape_only'):
            path = root/row['audio'][kind]
            if sha(path) != row['audio_sha256'][kind]:
                raise ValueError('Approved source audio changed')
            info = wave_info(path)
            if abs(info['frames']/info['sample_rate']*1000-row['duration_ms']) > .01:
                raise ValueError('Source audio and caption clock differ')
            if row['duration_ms'] > 300000:
                raise ValueError('Story exceeds the five-minute policy')
            protected[row['audio'][kind]] = row['audio_sha256'][kind]
    # Preserve all existing TOE versions, including the other machine's project.
    for path in root.glob('*.toe'):
        protected[path.name] = sha(path)
    write(work/'protected-inputs.json', protected)
    recipes = []
    reused_segments = 0
    converted_segments = 0
    normalized = {'voices_only': [], 'soundscape_only': []}
    for row in collection['stories']:
        for kind in normalized:
            path = root/row['audio'][kind]
            info = wave_info(path)
            filters = []
            if info['channels'] == 1:
                filters.append('pan=stereo|c0=c0|c1=c0')
            if kind == 'soundscape_only':
                # No overlap or timing shift at a story boundary; only a gentle
                # envelope on the derived ambient copy. Narration is untouched.
                end = row['duration_ms']/1000
                filters += ['afade=t=in:d=0.35', f'afade=t=out:st={end-.35:.6f}:d=0.35']
            recipe = dict(source_sha256=protected[row['audio'][kind]], sample_rate=RATE,
                          channels=2, sample_width=2, filters=filters)
            key = hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest()[:24]
            cached = work/'segments'/f'{key}.wav'
            receipt = cached.with_suffix('.json')
            cached.parent.mkdir(exist_ok=True)
            expected_frames = round(row['duration_ms']*RATE/1000)
            if not cached.exists() and not receipt.exists() and reuse is not None:
                previous = reuse/cached.name
                previous_receipt = previous.with_suffix('.json')
                if previous.exists() or previous_receipt.exists():
                    if (not previous.is_file() or not previous_receipt.is_file()
                            or read(previous_receipt).get('recipe') != recipe
                            or read(previous_receipt).get('sha256') != sha(previous)
                            or wave_info(previous) != dict(channels=2, sample_width=2, sample_rate=RATE, frames=expected_frames)):
                        raise ValueError('Held or changed earlier segment cache; never overwrite it')
                    cached, receipt = previous, previous_receipt
                    protected[cached.relative_to(root).as_posix()] = sha(cached)
                    protected[receipt.relative_to(root).as_posix()] = sha(receipt)
                    reused_segments += 1
            valid = (cached.exists() and receipt.exists() and read(receipt).get('sha256') == sha(cached)
                     and read(receipt).get('recipe') == recipe
                     and wave_info(cached)['frames'] == expected_frames)
            if not valid:
                if cached.exists() or receipt.exists():
                    raise ValueError('Held or changed playlist segment; use a fresh edition rather than overwrite')
                args = ['-i', str(path)]
                if filters:
                    args += ['-af', ','.join(filters)]
                temporary = cached.with_suffix('.tmp.wav')
                run_ffmpeg(ffmpeg, args+['-ar', str(RATE), '-ac', '2', '-c:a', 'pcm_s16le', str(temporary)])
                if wave_info(temporary)['frames'] != expected_frames:
                    raise ValueError('Resampling changed the exact story duration')
                temporary.replace(cached)
                write(receipt, dict(recipe=recipe, sha256=sha(cached)))
                converted_segments += 1
            normalized[kind].append(cached)
            recipes.append(read(receipt))
        print(f'Prepared {row["number"]}/{len(collection["stories"])}', flush=True)
    recipe = dict(version=1, sources=recipes, ambient_background_db=ambient_db,
                  narration_gain_db=0, limiter_peak=.95, duration_ms=sum(s['duration_ms'] for s in collection['stories']))
    key = hashlib.sha256(json.dumps(recipe, sort_keys=True).encode()).hexdigest()[:20]
    edition = output/key
    edition.mkdir(exist_ok=True)
    manifest_path = edition/'audio-manifest.json'
    files = {kind: edition/f'{kind.replace("_", "-")}.wav' for kind in normalized}
    files['combined'] = edition/'narration-and-ambient.wav'
    cached = read(manifest_path) if manifest_path.exists() else {}
    for kind, paths in normalized.items():
        if not files[kind].exists() or cached.get('audio_sha256', {}).get(kind) != sha(files[kind]):
            concatenate(paths, files[kind])
    if not files['combined'].exists() or cached.get('audio_sha256', {}).get('combined') != sha(files['combined']):
        temporary = files['combined'].with_suffix('.tmp.wav')
        graph = (f'[1:a]volume={ambient_db}dB[bed];[0:a][bed]'
                 'amix=inputs=2:duration=first:normalize=0:dropout_transition=0,'
                 'alimiter=limit=0.95:level=false:latency=true')
        run_ffmpeg(ffmpeg, ['-i', str(files['voices_only']), '-i', str(files['soundscape_only']),
                            '-filter_complex', graph, '-ar', str(RATE), '-c:a', 'pcm_s16le', str(temporary)])
        temporary.replace(files['combined'])
    expected = round(recipe['duration_ms']*RATE/1000)
    for file in files.values():
        if wave_info(file) != dict(channels=2, sample_width=2, sample_rate=RATE, frames=expected):
            raise ValueError('Playlist audio length or format mismatch')
    manifest = dict(kind='offline_reviewed_storytelling_playlist', story_count=len(collection['stories']),
                    recipe=recipe, audio={k:p.relative_to(root).as_posix() for k,p in files.items()},
                    audio_sha256={k:sha(p) for k,p in files.items()}, duration_ms=recipe['duration_ms'])
    write(manifest_path, manifest)
    manifest['plans'] = {}
    for mode in MODES:
        plan = flatten(collection, mode)
        plan.update(audio_file=manifest['audio']['voices_only'],
                    soundscape_audio_file=manifest['audio']['soundscape_only'],
                    combined_audio_file=manifest['audio']['combined'], audio_sha256=manifest['audio_sha256'])
        path = work/f'{mode}-visual-scenes.json'
        write(path, plan)
        manifest['plans'][mode] = dict(path=path.relative_to(root).as_posix(), sha256=sha(path),
                                     scenes=len(plan['scenes']), captions=len(plan['captions']))
    manifest['stories'] = flatten(collection, 'balanced')['playlist_stories']
    manifest['source_collection'] = str(collection_path).replace('\\', '/')
    manifest['source_collection_sha256'] = sha(collection_file)
    manifest['servers_started'] = False
    manifest['paid_calls'] = 0
    if Path(work_dir) != WORK or reuse_segments_from is not None:
        manifest['build_cache'] = dict(reused_previous_segments=reused_segments,
                                       converted_segments=converted_segments)
    manifest['editorial_review'] = 'Approved source stories/audio; visual render review remains pending'
    changed = [p for p,h in protected.items() if sha(root/p) != h]
    if changed:
        raise ValueError('Protected input changed: '+', '.join(changed))
    write(work/'protected-inputs.json', protected)
    write(work/'playlist.json', manifest)
    print(json.dumps(dict(stories=manifest['story_count'], duration_ms=manifest['duration_ms'],
                          plans=manifest['plans'], protected_inputs=len(protected), paid_calls=0)), flush=True)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collection', type=Path, default=DEFAULT_COLLECTION)
    parser.add_argument('--ffmpeg', type=Path)
    parser.add_argument('--ambient-db', type=float, default=0.)
    parser.add_argument('--work-dir', type=Path, default=WORK)
    parser.add_argument('--audio-dir', type=Path, default=AUDIO)
    parser.add_argument('--reuse-segments-from', type=Path)
    args = parser.parse_args()
    build(collection_path=args.collection, ffmpeg=args.ffmpeg, ambient_db=args.ambient_db,
          work_dir=args.work_dir, audio_dir=args.audio_dir, reuse_segments_from=args.reuse_segments_from)
