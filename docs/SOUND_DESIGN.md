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
- Long thematic beds carry a movement; a proposed handoff shorter than 15
  seconds is ignored and the preceding bed continues.

The episode-level disclosure is:

> All non-voice sounds are illustrative sound design. None are recordings of
> the people, places, or events described in the archived stories.

## Pipeline

```text
episode script + sound-design.json
  -> validate anchors, provenance, levels, fades, and durations
  -> provider-neutral generated-SFX jobs
  -> generated or licensed audio assets
  -> normalize every asset to 48 kHz stereo
  -> extend section beds across the exact speech timeline
  -> suppress short handoffs and inherit the preceding bed
  -> render voices-only at -16 LUFS
  -> render non-human-only at -23 LUFS
  -> duck selected sounds in the combined review mix
  -> write sound cues and disclosure into the timeline and transcripts
```

The cue sheet is reproducible editorial state and belongs with the episode.
Generated assets are cached separately. A changed prompt or generator model
creates a new cache key; it does not invalidate TTS.

## Pilot palette

The pilot cue sheet is
[`episodes/2013-12.01/sound-design.json`](../episodes/2013-12.01/sound-design.json).
Its 13 cues create a continuous but restrained recurring language:

- a nearly subliminal archival-air loop across the entire episode
- seven long movement-aware beds generated at the provider's 30-second maximum
- paper and quiet room tone for the cold open
- physical texture dissolving into scanner and digital detail
- a five-second show ident
- abstract distance and threshold ambience at movement changes
- two brief incomplete-data effects
- an intentionally nonspecific memory-of-place texture
- household-object textures for material nostalgia
- paper, machine noise, and “digital dust” under the close
- a restrained return of the ident

The prompts avoid recognizable alerts, brands, named locations, voices, and
literal reenactments.

## Continuous coverage

`continuous_background` in the cue sheet names one `base` cue and sets the
minimum eligible thematic span. Cues marked `section` are resolved against the
actual speech timeline, not estimated word counts:

1. The base cue is stretched by seamless looping from 00:00 to the final frame.
2. Section cues are ordered by their script anchors.
3. Any raw section shorter than 15 seconds is suppressed.
4. Each retained cue extends until the next retained cue, so a skipped section
   automatically inherits the previous ambience.
5. The timeline records every suppressed cue and its reason.

The base layer remains underneath section beds at a much lower gain. This
prevents accidental silence if a section cue is unavailable while keeping the
soundscape subtle enough for intimate speech.

## Provider strategy

The speech and sound-effects providers do not need to match. ElevenLabs is the
selected pilot generator because its separate Sound Effects
API accepts prompts, duration, and looping instructions. The documented API
limit is 30 seconds per generation, which is why long beds use short seamless
source clips and loop only in the local mixer.

The eight continuous sources request 240 seconds of generated audio: eight
30-second seamless loops. The five fixed structural cues reuse their existing
cached generations. Under ElevenLabs' published API rate of 11 credits per
specified second, the new continuous sources had a conservative ceiling of
2,640 credits and have been generated successfully.

Official references:

- [ElevenLabs Sound Effects overview](https://elevenlabs.io/docs/overview/capabilities/sound-effects)
- [ElevenLabs text-to-sound-effects API](https://elevenlabs.io/docs/api-reference/text-to-sound-effects/convert)
- [ElevenLabs sound-effects credit calculation](https://elevenlabs.io/docs/help-center/product/content-production/sound-effects/how-much-does-it-cost-to-generate-sound-effects)
- [ElevenLabs API authentication and key restrictions](https://elevenlabs.io/docs/api-reference/authentication)

Licensed field recordings remain preferable when a recognizable real-world
environment and strong provenance matter. Generated audio is particularly
useful for the project's abstract archival textures.

## Commands

Validate the pilot's editorial cue sheet:

```powershell
python -m home_podcast validate-sound-design `
  --sound-design .\episodes\2013-12.01\sound-design.json `
  --script .\episodes\2013-12.01\script.json
```

After selecting a generator, export its cached jobs:

```powershell
python -m home_podcast prepare-sfx `
  --sound-design .\episodes\2013-12.01\sound-design.json `
  --script .\episodes\2013-12.01\script.json `
  --provider elevenlabs `
  --model eleven_text_to_sound_v2
```

Inspect the current cache and paid-call estimate without a credential or API
request:

```powershell
python -m home_podcast generate-sfx `
  --jobs .\work\sfx\2013-12.01-jobs.jsonl
```

The command is a dry run unless `--execute` is present. Paid generation also
requires an explicit ceiling:

```powershell
$secureKey = Read-Host "ElevenLabs API key" -AsSecureString
$keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try {
  $env:ELEVENLABS_API_KEY = `
    [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
} finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
}
Remove-Variable secureKey, keyPointer

python -m home_podcast generate-sfx `
  --jobs .\work\sfx\2013-12.01-jobs.jsonl `
  --execute `
  --max-credits 2640

Remove-Item Env:ELEVENLABS_API_KEY
```

Never place the key in `podcast.json`, a shell command, a job file, or source
control. ElevenLabs supports API-key scope restrictions and credit quotas;
apply both in its dashboard. The local `--max-credits` check is an additional
guard, not a replacement for the provider quota.

Each response is cached before FFmpeg converts it to a 48 kHz stereo WAV. If
conversion is interrupted, the next run recovers from that raw cache instead
of purchasing the sound again. Completed WAV files are also skipped, making
the command safe to resume.

Once speech and effects exist:

```powershell
python -m home_podcast render-audio `
  --jobs .\work\tts\2013-12.01-jobs.jsonl `
  --sound-design .\episodes\2013-12.01\sound-design.json `
  --sfx-jobs .\work\sfx\2013-12.01-jobs.jsonl
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
