# Sound design

Recovered Homes treats non-voice audio as a separate production layer. Host
speech stays clean and cached. Ambience, transitions, spot effects, and the
series ident can then be changed without regenerating a voice line or altering
the source-grounded script. The renderer delivers synchronized voices-only and
non-human-only tracks, plus a combined review mix.

## Editorial policy

The sound layer may evoke distance, memory, paper, scanning, or an incomplete
web capture. It must not imply that the project possesses historical audio
from a source story.

- Every cue carries machine-readable provenance and an accessible transcript
  label.
- Generated ambience is disclosed as illustrative sound design.
- Exact quotations remain clear and are not staged as reenactments.
- Sensitive passages avoid literal trauma effects.
- A nearly subliminal base bed covers the complete episode while preserving the
  perception of quiet.
- The scene-driven plan assigns one relevant sound layer to every visual scene.
- Each scene sound starts at its visual boundary; a quiet base bed remains
  audible through the fades so the non-human stem never has a gap.

The episode-level disclosure is:

> All non-voice sounds are illustrative sound design. None are recordings of
> the people, places, or events described in the archived stories.

## Pipeline

```text
episode script + visual plan + timeline + sound-design-scenes.json
  -> validate one prompt-hashed cue per visual scene
  -> validate anchors, provenance, levels, fades, and exact coverage
  -> provider-neutral generated-SFX jobs
  -> generated or licensed audio assets
  -> normalize every asset to its cue loudness target at 48 kHz stereo
  -> extend each scene bed to the next exact visual boundary
  -> fade scene beds into the continuous base at every handoff
  -> render voices-only at -16 LUFS
  -> render non-human-only at -23 LUFS
  -> duck selected sounds in the combined review mix
  -> write sound cues and disclosure into the timeline and transcripts
```

The cue sheet is reproducible editorial state and belongs with the episode.
Generated assets are cached separately. A changed prompt or generator model
creates a new cache key; it does not invalidate TTS.

## Pilot palette

The current pilot cue sheet is
[`episodes/2013-12.01/sound-design-scenes.json`](../episodes/2013-12.01/sound-design-scenes.json).
It contains 91 generated cues:

- one nearly subliminal archival-air loop across the entire episode
- 90 prompt-specific beds aligned one-to-one with the visual sequencer
- source generation equal to the scene duration, capped at 30 seconds
- fades at every visual boundary with the base ambience underneath

Each scene cue records its `visual_scene_id` and the SHA-256 hash of the visual
prompt from which it was composed. If a visual prompt changes, the scene-sound
validator rejects the stale cue sheet. Prompts explicitly exclude speech,
singing, music, recognizable alerts, and literal reenactment. The original
13-cue `sound-design.json` remains available as the earlier broad-movement
audition.

## Continuous coverage

`continuous_background` in the cue sheet names one `base` cue. Cues marked
`section` are resolved against the actual speech timeline and visual plan, not
estimated word counts:

1. The base cue is stretched by seamless looping from 00:00 to the final frame.
2. All 90 visual scenes have exactly one section cue.
3. Every section cue resolves to the same start and duration as its visual.
4. The scene cue fades in and out while the lower base bed continues beneath it.
5. The complete coverage is checked from 00:00 through 32:24.160.

`gain_db` is interpreted as the cue's integrated-loudness target, not as blind
attenuation of an unknown provider level. This keeps unusually quiet generated
assets audible and makes rerenders consistent across providers. `mix_gain_db`
is an optional bounded post-normalization trim for sparse assets whose long
silences make integrated normalization ineffective.

Delayed cue inputs are padded to the complete reviewed timeline before they are
summed. The mixer compensates for legacy FFmpeg `amix` normalization at unity
gain, preventing future silent inputs from making early scenes progressively
quieter. The base layer remains underneath section beds at a lower but
perceptible level, preventing accidental silence while keeping the soundscape
subtle enough for intimate speech.

## Provider strategy

The speech and sound-effects providers do not need to match. ElevenLabs is the
selected pilot generator because its separate Sound Effects
API accepts prompts, duration, and looping instructions. The documented API
limit is 30 seconds per generation, which is why long beds use short seamless
source clips and loop only in the local mixer.

The completed scene-driven plan contains 1,956.319 seconds across 91 generated
jobs. All 91 are cached, so the current dry run reports zero pending calls and
zero pending credits. The public portable handoff retains the original
compressed provider responses with cache keys and SHA-256 hashes; it can
reconstruct the normalized WAV cache locally without an API key.

Official references:

- [ElevenLabs Sound Effects overview](https://elevenlabs.io/docs/overview/capabilities/sound-effects)
- [ElevenLabs text-to-sound-effects API](https://elevenlabs.io/docs/api-reference/text-to-sound-effects/convert)
- [ElevenLabs sound-effects credit calculation](https://elevenlabs.io/docs/help-center/product/content-production/sound-effects/how-much-does-it-cost-to-generate-sound-effects)
- [ElevenLabs API authentication and key restrictions](https://elevenlabs.io/docs/api-reference/authentication)

Licensed field recordings remain preferable when a recognizable real-world
environment and strong provenance matter. Generated audio is particularly
useful for the project's abstract archival textures.

## Commands

Rebuild and validate the pilot's scene-driven cue sheet:

```powershell
python .\scripts\build_pilot_scene_soundscape.py

python -m home_podcast validate-sound-design `
  --sound-design .\episodes\2013-12.01\sound-design-scenes.json `
  --script .\episodes\2013-12.01\script.json

python -m home_podcast validate-scene-soundscape `
  --sound-design .\episodes\2013-12.01\sound-design-scenes.json `
  --visuals .\episodes\2013-12.01\visuals\2013-12.01-visual-scenes.json `
  --timeline .\episodes\2013-12.01\audio\2013-12.01-timeline.json
```

After selecting a generator, export its cached jobs:

```powershell
python -m home_podcast prepare-sfx `
  --sound-design .\episodes\2013-12.01\sound-design-scenes.json `
  --script .\episodes\2013-12.01\script.json `
  --output .\work\sfx\2013-12.01-scene-jobs.jsonl `
  --provider elevenlabs `
  --model eleven_text_to_sound_v2
```

Inspect the current cache and paid-call estimate without a credential or API
request:

```powershell
python -m home_podcast generate-sfx `
  --jobs .\work\sfx\2013-12.01-scene-jobs.jsonl
```

The command is a dry run unless `--execute` is present. Paid generation also
requires an explicit ceiling. On Windows, use the one-time masked credential
prompt and resumable production wrapper:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\save_elevenlabs_key.ps1

powershell -ExecutionPolicy Bypass `
  -File .\scripts\run_scene_sfx_generation.ps1 `
  -MaxCredits <exact estimated_credits from the dry run>
```

Never place the key in `podcast.json`, a shell command, a job file, or source
control. ElevenLabs supports API-key scope restrictions and credit quotas;
apply both in its dashboard. The local `--max-credits` check is an additional
guard, not a replacement for the provider quota. The helper stores only a
Windows DPAPI-encrypted blob under
`%LOCALAPPDATA%\RecoveredHomes\secrets\elevenlabs.dpapi`, outside the
repository. Only the same Windows user on the same PC can decrypt it; enter the
key once again after moving to another computer.

Each response is cached before FFmpeg converts it to a 48 kHz stereo WAV. If
conversion is interrupted, the next run recovers from that raw cache instead
of purchasing the sound again. Completed WAV files are also skipped, making
the command safe to resume.

For a cross-PC handoff, validate and restore the tracked raw-response set:

```powershell
python .\scripts\sync_pilot_sfx_cache.py validate
python .\scripts\sync_pilot_sfx_cache.py restore
```

`restore` hashes all 91 files, rebuilds the current job list, and permits only
zero-credit local recovery. A changed or missing cue stops the command rather
than making a provider call.

After any authorized paid replacement on the production computer, refresh and
check the tracked response set before committing:

```powershell
python .\scripts\sync_pilot_sfx_cache.py export
python .\scripts\sync_pilot_sfx_cache.py validate
```

Once the effects exist, render against the reviewed timeline and voices-only
master. This avoids rebuilding speech from older provider jobs after the
editorial timeline has been refined:

```powershell
python -m home_podcast render-soundscape `
  --timeline .\episodes\2013-12.01\audio\2013-12.01-timeline.json `
  --sound-design .\episodes\2013-12.01\sound-design-scenes.json `
  --sfx-jobs .\work\sfx\2013-12.01-scene-jobs.jsonl `
  --voices-audio .\episodes\2013-12.01\audio\2013-12.01-voices-only-master.wav
```

With sound design, the output directory contains:

- `2013-12.01-voices-only-master.wav`
- `2013-12.01-voices-only.mp3`
- `2013-12.01-soundscape-only-master.wav`
- `2013-12.01-soundscape-only.mp3`
- `2013-12.01-master.wav` and `2013-12.01.mp3` as the combined review mix

All tracks start at the same sample and have the same duration. Omitting
`--sound-design` and `--sfx-jobs` produces the voices-only deliverable and keeps
the legacy combined output names as aliases.
