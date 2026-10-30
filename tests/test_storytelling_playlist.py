from __future__ import annotations

import copy
from pathlib import Path
import runpy
import tempfile
from types import SimpleNamespace
import unittest

from scripts.build_storytelling_playlist import build, flatten
from touchdesigner.storytelling_playlist_sequencer import PodcastSequencer
from touchdesigner import execute_callbacks, show_control_callbacks


def collection():
    rows = []
    for number, duration in ((1, 40000), (2, 50000)):
        plan = dict(contract_version=1, touchdesigner_version='2025.32820', project_variant='3080',
                    duration_ms=duration, timing_policy={}, prompt_policy={}, grounding_policy={},
                    scenes=[], captions=[dict(caption_id='c1', start_ms=0, end_ms=3000, text='My memory')])
        for index, (start, end) in enumerate(((0, 20000), (20000, duration))):
            plan['scenes'].append(dict(scene_id=f's{index}', start_ms=start, end_ms=end,
                duration_ms=end-start, segment_ids=['c1'], crossfade_in_ms=8000,
                speech_anchor={'not_before_ms': start},
                ambient_context=[dict(start_ms=0, end_ms=duration)],
                personal_story_excerpt='My memory', section_ids=['001'],
                prompt={'chunks': [{'text': f'memory {number} scene {index}'}], 'seed': number}))
        rows.append(dict(number=number, narration_id=f'story-{number}', title=f'Story {number}',
                         duration_ms=duration, paths={mode: dict(plan=copy.deepcopy(plan), path=f'{number}-{mode}.json', sha256='hash')
                         for mode in ('original', 'human_figures', 'balanced')}))
    return {'stories': rows}


class PlaylistTests(unittest.TestCase):
    def test_offset_only_and_sources_immutable(self):
        source = collection()
        before = copy.deepcopy(source)
        result = flatten(source, 'balanced')
        self.assertEqual(source, before)
        self.assertNotIn('narration_id', result)
        self.assertEqual(result['duration_ms'], 90000)
        self.assertEqual(result['episode_id'], 'real-december-reviewed-2')
        self.assertEqual(result['scenes'][2]['start_ms'], 40000)
        self.assertEqual(result['scenes'][2]['speech_anchor']['not_before_ms'], 40000)
        self.assertEqual(result['scenes'][2]['ambient_context'][0]['end_ms'], 90000)
        self.assertEqual(result['captions'][1]['start_ms'], 40000)
        self.assertEqual(len({s['scene_id'] for s in result['scenes']}), 4)
        self.assertEqual(result['scenes'][2]['prompt'], source['stories'][1]['paths']['balanced']['plan']['scenes'][0]['prompt'])

    def test_no_cross_story_prompt_mix_even_with_large_override(self):
        seq = PodcastSequencer(flatten(collection(), 'balanced'))
        for fade in (0, 8000, 30000, 90000):
            for time, expected in ((39999, 'story-1'), (40000, 'story-2'), (40001, 'story-2'), (89999, 'story-2'), (0, 'story-1')):
                frame = seq.at(time, crossfade_ms=fade)
                self.assertTrue(all(layer.scene_id.startswith(expected+'--') for layer in frame.prompt_layers))
        self.assertEqual(seq.at(40000, crossfade_ms=90000).crossfade_ms, 0)

    def test_story_edge_envelope_and_navigation(self):
        seq = PodcastSequencer(flatten(collection(), 'original'))
        self.assertEqual(seq.output_opacity_at(0), 0)
        self.assertEqual(seq.output_opacity_at(40000), 0)
        self.assertEqual(seq.output_opacity_at(90000), 0)
        self.assertEqual(seq.output_opacity_at(41000), 1)
        self.assertEqual(seq.output_opacity_at(40000, 0), 1)
        self.assertAlmostEqual(seq.output_opacity_at(40500), .5)
        self.assertEqual(seq.navigate(45000, 1), 0)
        self.assertEqual(seq.navigate(0, -1), 40000)
        self.assertEqual(seq.navigate(45000, 1, loop=False), 40000)
        self.assertEqual(seq.story_at(39999)['number'], 1)
        self.assertEqual(seq.story_at(40000)['number'], 2)

    def test_reject_gaps_and_overlaps(self):
        for delta in (-1, 1):
            plan = flatten(collection(), 'balanced')
            plan['playlist_stories'][1]['start_ms'] += delta
            with self.assertRaises(ValueError):
                PodcastSequencer(plan)

    def test_three_audio_modes_and_legacy_aliases(self):
        for module in (execute_callbacks, show_control_callbacks):
            for value in (2, '2', 'combined', 'both', 'mix', 'Narration + Ambient'):
                self.assertEqual(module._audio_source_index(value), 2)
            for value in (1, 'soundscape', 'nonhuman'):
                self.assertEqual(module._audio_source_index(value), 1)
            for value in (0, 'voices', '', 'unexpected'):
                self.assertEqual(module._audio_source_index(value), 0)

    def test_edition_output_paths_cannot_escape_project(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for options in (
                {'work_dir': 'work/storytelling-real-december'},
                {'work_dir': '../outside'},
                {'audio_dir': 'audio/storytelling-real-december/../../outside'},
                {'reuse_segments_from': '../outside/segments'},
                {'reuse_segments_from': 'work/storytelling-real-december/not-segments'},
            ):
                with self.subTest(options=options), self.assertRaises(ValueError):
                    build(root=root, **options)

    def test_installer_selects_persisted_playlist_without_changing_legacy_default(self):
        installer = Path(__file__).resolve().parents[1]/'touchdesigner/install_storytelling_playlist.py'
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            project = SimpleNamespace(folder=str(root))
            legacy = runpy.run_path(str(installer), init_globals={'project': project, 'op': lambda path: None})
            self.assertEqual(legacy['WORK'], root/'work/storytelling-real-december/playlist-35-2026-10-29')
            manifest = root/'work/storytelling-real-december/playlist-45-2026-10-29/playlist.json'
            connector = SimpleNamespace(par=SimpleNamespace(Playlistmanifest=SimpleNamespace(eval=lambda: str(manifest))))
            current = runpy.run_path(str(installer), init_globals={'project': project, 'op': lambda path: connector})
            self.assertEqual(current['WORK'], manifest.parent)
            for value in ('../playlist.json', 'work/storytelling-real-december/playlist.json',
                          'work/storytelling-real-december/edition/wrong.json'):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    current['_resolve_playlist_work'](root, value)


if __name__ == '__main__':
    unittest.main()
