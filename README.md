# Recovered Homes

Recovered Homes is an incremental production pipeline for a popular,
rotating-cast podcast about home, belonging, digital history, and digital
archaeology.

The canonical source snapshot is tracked in `data/exports`. It contains only
`stories_*.md` files copied from the sibling extractor project and deliberately
excludes `matches` exports and the compressed JSONL export.

The system is designed around three promises:

1. New or changed stories are processed incrementally.
2. Every podcast claim remains traceable to archived source evidence.
3. Published episodes remain reproducible even when older crawl months receive
   late-arriving stories.

## Current pipeline

```text
stories_*.md
  → incremental SQLite catalog
  → cached story-analysis jobs
  → thematic crawl-month proposal
  → locked episode evidence + frozen rotating cast
  → grounded multi-host script
  → cached segment-level speech jobs
  → optional provenance-tracked sound-design cues
  → mixed and normalized WAV + MP3
  → Markdown + WebVTT + SRT transcripts
```

Deterministic code owns parsing, WARC dates, IDs, history, manifests, caching,
audio assembly, and transcripts. Codex is the default workspace for semantic
story cards, scriptwriting/editorial passes, and visual prompts. Configured
text-generation providers remain opt-in automation fallbacks. ElevenLabs
handles requested voice and sound performance.

## Codex-native workflow

For normal interactive production, no text-generation API key is required.
Ask Codex to analyze new stories, build an episode script, or generate visual
prompts. Repository-level instructions in [`AGENTS.md`](AGENTS.md) make the
workflow incremental and require the existing importers and validators.

The short user-facing guide, supported tasks, and provider boundaries are in
[`docs/CODEX_WORKFLOW.md`](docs/CODEX_WORKFLOW.md).

## Quick start

The project currently has no third-party Python dependencies and supports
Python 3.10 or newer.

```powershell
python -m home_podcast doctor
python -m home_podcast ingest
python -m home_podcast status
```

The configured source directory is:

```text
data/exports
```

This makes a GitHub clone self-contained. To move the project to another
computer, including rebuilding the local catalog and restoring cached story
analysis, follow [`docs/PORTABLE_SETUP.md`](docs/PORTABLE_SETUP.md).

Running `ingest` repeatedly is safe. Unchanged stories retain their catalog
records and cached analysis. Changed stories create a new version. Stories no
longer present in an export are marked missing rather than deleted.

## Crawl-month archive volumes

The exact timestamp is parsed from the WARC filename:

```text
CC-MAIN-20131204133352-...
          └─ 2013-12-04 13:33:52 UTC
```

The resulting archive volume is `2013-12`. This is the page capture month,
never an assertion about when the story was written or published.

Inspect one month:

```powershell
python -m home_podcast status --month 2013-12
```

## Story analysis

The default Codex-native path uses `export-analysis` and `import-cards` as
described in `AGENTS.md`. The configured external automation fallback is
Capriole Fable 5. Supply its credential only through the process environment:

```powershell
$secureKey = Read-Host "Capriole API key" -AsSecureString
$keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)
try {
  $env:CAPRIOLE_API_KEY = `
    [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
} finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
}
Remove-Variable secureKey, keyPointer
```

The complete December snapshot, analyzed pool, and one-theme pilot are frozen
separately:

```powershell
python -m home_podcast snapshot-volume `
  --month 2013-12 `
  --label full-corpus

python -m home_podcast snapshot-volume `
  --month 2013-12 `
  --label analyzed-pool `
  --analyzed-only

python -m home_podcast snapshot-volume `
  --month 2013-12 `
  --label pilot `
  --theme exile-return-nostalgia

python -m home_podcast export-analysis `
  --cohort .\cohorts\2013-12-pilot.json `
  --output .\work\analysis\2013-12-pilot-jobs.jsonl

python -m home_podcast analyze `
  --input .\work\analysis\2013-12-pilot-jobs.jsonl `
  --workers 3
```

For the current pilot, all 27 selected records already have story cards, so no
additional analysis request is required. The other 64 analyzed stories remain
in `cohorts/2013-12-analyzed-pool.json`; the complete 421-story corpus remains
in `cohorts/2013-12-full-corpus.json`.

The analyzer caches each completed model response separately and imports it
immediately. Rerunning the command skips completed work and retries only
unfinished or failed stories. Start with three workers; raise concurrency only
when the provider's documented traffic limits support it. Clear the environment
variable when the run is done:

```powershell
Remove-Item Env:CAPRIOLE_API_KEY
```

The exported JSONL contains one story per line, including provenance, the
controlled theme vocabulary, and the required result contract. The analysis
model follows `prompts/story_analysis.md` and returns data shaped like:

```json
{
  "story_id": "story-...",
  "content_hash": "...",
  "analysis": {
    "eligible": true,
    "exclusion_reason": null,
    "summary": "...",
    "primary_theme": "family-inheritance",
    "secondary_themes": ["memory-archive"],
    "theme_fit": 0.93,
    "anchor_score": 0.81,
    "emotional_tone": "reflective",
    "digital_archaeology_angles": ["..."],
    "memorable_passages": ["verbatim source excerpt"],
    "sensitivity_notes": [],
    "translation_needed": false,
    "pronunciation_items": [],
    "usage_recommendation": "anchor"
  }
}
```

Provider-produced cards can also be imported manually:

```powershell
python -m home_podcast import-cards .\cards.jsonl `
  --analyzer PROVIDER_NAME `
  --analyzer-version MODEL_AND_PROMPT_VERSION
```

Cards whose story content changed after analysis are skipped. They will
automatically reappear in the next export.

Current cards can be preserved without the rebuildable SQLite catalog:

```powershell
python -m home_podcast export-cards `
  --output .\data\story_cards\current-cards.jsonl

python -m home_podcast import-cards `
  .\data\story_cards\current-cards.jsonl
```

The portable JSONL embeds its analyzer provenance. Import still validates every
story ID, content hash, controlled theme, and verbatim source passage.

## Theme and installment planning

After the month has story cards:

```powershell
python -m home_podcast plan `
  --month 2013-12 `
  --cohort .\cohorts\2013-12-pilot.json
```

The pilot cohort contains only the selected theme, so the regular multi-theme
planner produces one installment containing all 27 eligible stories. Future
cohorts can still produce multiple themed sub-episodes.

The proposal is editorial input, not a published manifest. During the pilot,
lock the preferred installment before script generation:

```powershell
python -m home_podcast lock-episode `
  --proposal .\work\planning\2013-12-proposal.json `
  --episode 2013-12.01

python -m home_podcast cast-episode `
  --episode 2013-12.01
```

This creates `episodes/2013-12.01/manifest.json` with the exact story IDs and
content hashes. The command refuses to replace that manifest with different
content. Published manifests should never be rewritten.

## Script production

Prepare a bounded evidence packet for one proposed installment:

```powershell
python -m home_podcast prepare-script `
  --manifest .\episodes\2013-12.01\manifest.json `
  --episode 2013-12.01
```

The script model receives this packet plus `prompts/script_writer.md`. Its
output must conform to `contracts/script.schema.json`.

Generate the episode from its locked evidence and editorial outline:

```powershell
$env:CAPRIOLE_API_KEY = "..."
python -m home_podcast generate-script `
  --evidence .\work\scripts\2013-12.01-evidence.json `
  --outline .\episodes\2013-12.01\outline.json
Remove-Item Env:CAPRIOLE_API_KEY
```

The generator uses Capriole's protocol-compatible streaming endpoint and caches
each outline section separately. A validated script is written to
`episodes/2013-12.01/script.json`; an invalid candidate remains under `work/`
with a validation report and does not replace the episode script.

Apply the reviewed, hash-bound pilot trim without another model call:

```powershell
python -m home_podcast trim-script `
  --script .\episodes\2013-12.01\script.json `
  --evidence .\work\scripts\2013-12.01-evidence.json `
  --plan .\episodes\2013-12.01\trim-plan.json
```

Then polish the trimmed, validated script into a more natural conversation
while locking speakers, citations, quotations, pronunciations, pauses, and
section order:

```powershell
$env:CAPRIOLE_API_KEY = "..."
python -m home_podcast polish-script `
  --script .\episodes\2013-12.01\script.json `
  --evidence .\work\scripts\2013-12.01-evidence.json `
  --cast .\episodes\2013-12.01\cast.json
Remove-Item Env:CAPRIOLE_API_KEY
```

The polisher caches each original generation section independently. Audible
reactions such as a chuckle, sigh, or exhale are stored in TTS-only delivery
metadata and do not appear as bracketed text in transcripts. The pilot trim
plan is now a historical pre-polish record and must not be reapplied to the
polished script.

Validate story coverage, speakers, citations, and exact quotations:

```powershell
python -m home_podcast validate-script `
  --script .\episodes\2013-12.01\script.json `
  --evidence .\work\scripts\2013-12.01-evidence.json
```

Validation fails if even one selected story has no traceable use.

## Speech, sound design, audio, and transcripts

Each new episode selects a role-matched lineup from
`config/voice_roster.json`, maximizes distinct verified accents, and freezes
the result in `episodes/<episode>/cast.json`. The same episode always reuses
its saved cast, while later episodes rotate to different people. Accent
selection comes from the voice's verified metadata and listening review, never
from imitation instructions in the script. Create one cached speech job per
speaking turn:

```powershell
python -m home_podcast prepare-tts `
  --script .\episodes\2013-12.01\script.json `
  --cast .\episodes\2013-12.01\cast.json `
  --provider elevenlabs `
  --model eleven_v3

# Dry run: no credential and no provider call
python -m home_podcast generate-tts `
  --jobs .\work\tts\2013-12.01-jobs.jsonl
```

Paid speech generation is opt-in and requires both `--execute` and an explicit
`--max-credits` ceiling:

```powershell
$env:ELEVENLABS_API_KEY = "..."
python -m home_podcast generate-tts `
  --jobs .\work\tts\2013-12.01-jobs.jsonl `
  --execute `
  --max-credits 27125
Remove-Item Env:ELEVENLABS_API_KEY
```

The adapter saves the raw provider response before producing a 48 kHz stereo
WAV. Rerunning uses the valid WAV cache, or recovers from the raw response
without another paid call. The cache key includes provider, model, voice,
rendered text, supported continuity context, delivery direction, and
pronunciation settings, so only changed lines require regeneration.

The approved pilot cast is Maya/Bella, Theo/Roger, and Lina/Lily. Its
three-host casting audition is versioned at
`episodes/2013-12.01/voice-audition.json`. Its generated, level-matched
listening copies remain local and ignored under
`work/tts/audition-2013-12.01/`.

The Creator subscription enables 192 kbps API output and community Voice
Library auditions. Prepare the same-script comparison for the nine
metadata-screened international English candidates:

```powershell
python -m home_podcast prepare-voice-audition `
  --audition .\episodes\2013-12.01\accent-voice-audition.json `
  --candidates .\config\accent_voice_candidates.json

# Dry run reports the remaining credit ceiling
python -m home_podcast generate-tts `
  --jobs .\work\tts\accent-voice-audition-2026-07-jobs.jsonl
```

The local audition covers Canadian, Chinese-influenced, French-influenced,
Indian, Irish, Nigerian, Scottish, South African, and Spanish-influenced
English. Candidates remain outside the production roster until their samples
pass the listening rubric. See
[docs/ACCENT_CASTING.md](docs/ACCENT_CASTING.md).

For natural interaction, test a short excerpt through ElevenLabs Text to
Dialogue before rendering the complete episode. This preserves the surrounding
speakers and emotional arc in one provider call instead of synthesizing every
short line in isolation:

```powershell
python -m home_podcast prepare-dialogue-audition `
  --audition .\episodes\2013-12.01\continuity-audition.json `
  --cast .\episodes\2013-12.01\cast.json

# Dry run: reports both Natural and Creative variants
python -m home_podcast generate-dialogue-audition `
  --jobs .\work\tts\2013-12.01-expressive-dialogue-audition-dialogue-jobs.jsonl

$env:ELEVENLABS_API_KEY = "..."
python -m home_podcast generate-dialogue-audition `
  --jobs .\work\tts\2013-12.01-expressive-dialogue-audition-dialogue-jobs.jsonl `
  --execute `
  --max-credits 3520
Remove-Item Env:ELEVENLABS_API_KEY
```

Each variant contains eight turns and 1,760 rendered characters, below the
provider's 2,000-character reliability recommendation. Provider responses,
normalized cache files, and listening copies remain ignored locally.

A more adventurous Creative+ version uses the same eight source-preserving
turns with richer emotional direction and moderate style exaggeration:

```powershell
python -m home_podcast prepare-dialogue-audition `
  --audition .\episodes\2013-12.01\creative-plus-audition.json `
  --cast .\episodes\2013-12.01\cast.json
```

It runs 115.41 seconds and used 1,884 credits. Creative+ is the selected pilot
performance style.

Prepare the complete episode as movement-aware contextual chunks. The
timestamped dialogue endpoint returns one timing range per scripted turn, so
the final transcript and sound-cue anchors remain exact without a second
transcription call:

```powershell
python -m home_podcast prepare-dialogue-episode `
  --script .\episodes\2013-12.01\script.json `
  --cast .\episodes\2013-12.01\cast.json `
  --performance .\episodes\2013-12.01\creative-plus-audition.json `
  --variant creative-plus

# Dry run: 17 calls, 27,125-character conservative ceiling
python -m home_podcast generate-dialogue-episode `
  --jobs .\work\tts\2013-12.01-dialogue-episode-jobs.jsonl

$env:ELEVENLABS_API_KEY = "..."
python -m home_podcast generate-dialogue-episode `
  --jobs .\work\tts\2013-12.01-dialogue-episode-jobs.jsonl `
  --execute `
  --max-credits 27125
Remove-Item Env:ELEVENLABS_API_KEY
```

Generation is resumable by chunk. Audio and timestamp data are cached
separately before normalization, and neither contains the API key. The pilot
completed all 17 chunks and 128 turns in 30:44.72. ElevenLabs reported 14,921
credits for the clean pass, below the conservative 27,125-credit ceiling.

The current speech-provider shortlist and pilot audition recommendation are in
[docs/SPEECH_PROVIDERS.md](docs/SPEECH_PROVIDERS.md).
The selected one-theme pilot and its TTS cost model are in
[docs/PILOT_EPISODE.md](docs/PILOT_EPISODE.md).

Non-voice audio is an independent layer. The current scene-driven pilot plan
contains one nearly subliminal full-episode base bed and one relevant synthetic
sound layer for each of the 90 visual prompts. All cues are illustrative sound
design, not simulated historical or location recordings. Rebuild and validate
the plan:

```powershell
python .\scripts\build_pilot_scene_soundscape.py

python -m home_podcast validate-sound-design `
  --sound-design .\episodes\2013-12.01\sound-design-scenes.json `
  --script .\episodes\2013-12.01\script.json

python -m home_podcast validate-scene-soundscape `
  --sound-design .\episodes\2013-12.01\sound-design-scenes.json `
  --visuals .\episodes\2013-12.01\visuals\2013-12.01-visual-scenes.json `
  --timeline .\episodes\2013-12.01\audio\2013-12.01-timeline.json

python -m home_podcast prepare-sfx `
  --sound-design .\episodes\2013-12.01\sound-design-scenes.json `
  --script .\episodes\2013-12.01\script.json `
  --output .\work\sfx\2013-12.01-scene-jobs.jsonl `
  --provider elevenlabs `
  --model eleven_text_to_sound_v2

# Dry run: no credential and no provider call
python -m home_podcast generate-sfx `
  --jobs .\work\sfx\2013-12.01-scene-jobs.jsonl
```

The cue contract, provider research, provenance policy, and mixing behavior are
documented in [docs/SOUND_DESIGN.md](docs/SOUND_DESIGN.md).
Paid generation is opt-in and requires both `--execute` and an explicit
`--max-credits` ceiling. Provider keys are read only from environment
variables and must never be committed. The completed pilot now has all 91
generated cues cached and the current dry run reports zero pending calls. If a
future cue changes, run the dry run again and use its exact new
`estimated_credits` value as the ceiling.

On Windows, save the key once with a masked prompt and run the resumable
production wrapper:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .\scripts\save_elevenlabs_key.ps1

powershell -ExecutionPolicy Bypass `
  -File .\scripts\run_scene_sfx_generation.ps1 `
  -MaxCredits <exact estimated_credits from the dry run>
```

The encrypted DPAPI blob lives under the current user's local application-data
folder, outside the repository. It can be decrypted only by that Windows user
on that PC and is not part of the cross-PC handoff.

The public handoff includes the 91 original compressed provider responses—not
credentials, request IDs, or account metadata—so a new computer can restore
the exact resumable WAV cache without another paid call:

```powershell
python .\scripts\sync_pilot_sfx_cache.py validate
python .\scripts\sync_pilot_sfx_cache.py restore
```

The restore verifies every response against the current cue cache key and
SHA-256 digest, then uses local FFmpeg conversion. It refuses to proceed if any
current cue is absent, so it cannot silently fall through to paid generation.
After generating or replacing a cue on the production computer, refresh the
handoff before committing:

```powershell
python .\scripts\sync_pilot_sfx_cache.py export
python .\scripts\sync_pilot_sfx_cache.py validate
```

Once every generated-effect clip exists, render against the reviewed pilot
timeline and its already-approved voices-only master:

```powershell
python -m home_podcast render-soundscape `
  --timeline .\episodes\2013-12.01\audio\2013-12.01-timeline.json `
  --sound-design .\episodes\2013-12.01\sound-design-scenes.json `
  --sfx-jobs .\work\sfx\2013-12.01-scene-jobs.jsonl `
  --voices-audio .\episodes\2013-12.01\audio\2013-12.01-voices-only-master.wav
```

The renderer uses FFmpeg to preserve the reviewed speech master and timeline,
normalize sound assets to 48 kHz stereo, extend every scene bed to its exact
visual boundary, fade it down to the continuous safety bed at each handoff, and
create synchronized 192 kbps deliverables:

- `<episode>-voices-only.mp3`
- `<episode>-soundscape-only.mp3`
- `<episode>.mp3` as a combined review mix

All delayed cue inputs are padded to the reviewed timeline before summing. The
mixer restores unity gain after legacy FFmpeg `amix` normalization, so future
silent cues cannot attenuate early scenes. `mix_gain_db` provides a bounded
post-normalization trim for unusually sparse assets, and the continuous base
retains an audible safety floor beneath them.

The non-human stem is continuous because a quiet base loop covers any interval
without a retained thematic bed. Omitting the two sound-design arguments still
produces the voices-only render.

The repository tracks the synchronized distribution stems needed by
TouchDesigner:

- `episodes/2013-12.01/audio/2013-12.01-voices-only.mp3`
- `episodes/2013-12.01/audio/2013-12.01-soundscape-only.mp3`

Large intermediate WAV masters and the combined review MP3 remain local and
rebuildable.

Generate deliverable transcripts:

```powershell
python -m home_podcast transcript `
  --timeline .\episodes\2013-12.01\audio\2013-12.01-timeline.json

python -m home_podcast transcript `
  --timeline .\episodes\2013-12.01\audio\2013-12.01-timeline.json `
  --speech-only
```

Outputs include speaker-labeled Markdown, WebVTT, and SRT with accessible
non-speech labels, the sound-design disclosure, and a story-to-script source
map. The `--speech-only` variant omits sound cues and writes distinct
`voices-only` transcript, VTT, and SRT files for the visual pipeline.

## Real-time visual sequencer

Build long visual scenes from the speech timeline, preserving exact caption
timings and attaching the matching story evidence:

```powershell
python -m home_podcast prepare-visuals `
  --timeline .\episodes\2013-12.01\audio\2013-12.01-timeline.json `
  --min-scene-seconds 15 `
  --crossfade-seconds 5

python -m home_podcast validate-visuals `
  --visuals .\episodes\2013-12.01\visuals\2013-12.01-visual-scenes.json
```

The current pilot plan contains 90 long scenes across 32:24.160. It began with
36 scenes and was expanded at speech boundaries so each image remains useful
without racing ahead of its spoken passage. Short story runs are merged into a
neighboring scene rather than flashing a new image. Every scene stores
captions, story IDs, location evidence, identity evidence, a stable seed, and
crossfade timing. The prompt jobs under `work/visuals/` carry the full evidence
text for an offline LLM pass; identity or location must never be inferred when
the source does not support it.

Run the evidence-grounded prompt pass offline from TouchDesigner:

```powershell
# Safe dry run: validates all jobs and the locally cached SDXL tokenizers.
python -m home_podcast generate-visual-prompts `
  --jobs .\work\visuals\2013-12.01-prompt-jobs.jsonl `
  --visuals .\episodes\2013-12.01\visuals\2013-12.01-visual-scenes.json

# Paid, resumable generation. The explicit ceiling prevents surprise calls.
$env:CAPRIOLE_API_KEY = Read-Host "Capriole API key"
python -m home_podcast generate-visual-prompts `
  --jobs .\work\visuals\2013-12.01-prompt-jobs.jsonl `
  --visuals .\episodes\2013-12.01\visuals\2013-12.01-visual-scenes.json `
  --execute `
  --max-calls 36
Remove-Item Env:CAPRIOLE_API_KEY
```

The runner uses Claude Opus 4.6 through the configured Capriole endpoint. It
caches every raw response before parsing, resumes completed scenes, and
validates prompt length with both tokenizers from the locally cached SDXL
Turbo model. A prompt must contain exactly one 68–75 content-token narrative
chunk. Claimed identities and locations must cite verbatim text from the
corresponding story. Generated scenes remain marked for editorial review.
Use `--retry-invalid` only when you intentionally want to pay to replace a
cached invalid response.

For the default no-network Codex path, write one result object per job to a
JSONL file and import it through the same evidence and SDXL-token gates:

```powershell
python -m home_podcast import-visual-prompts `
  --input .\work\codex\visuals\2013-12.01-results.jsonl `
  --jobs .\work\visuals\2013-12.01-prompt-jobs-dense-v2.jsonl `
  --visuals .\episodes\2013-12.01\visuals\2013-12.01-visual-scenes.json `
  --model-label codex-interactive
```

To make an already generated visual plan denser without regenerating accepted
prompts, expand long scenes at speech boundaries:

```powershell
python -m home_podcast expand-visuals `
  --source-visuals .\episodes\2013-12.01\visuals\2013-12.01-visual-scenes-36-scene-backup.json `
  --timeline .\episodes\2013-12.01\audio\2013-12.01-timeline.json `
  --output .\episodes\2013-12.01\visuals\2013-12.01-visual-scenes.json `
  --jobs .\work\visuals\2013-12.01-prompt-jobs-dense-v2.jsonl `
  --min-scene-seconds 15 `
  --max-scene-seconds 35
```

The expansion retains one validated prompt per original scene, assigns it to
the best-matching child passage, and emits jobs only for complementary images.
Each new job includes the retained composition it must avoid. The maximum is a
target rather than a hard cut: the pipeline keeps a scene slightly longer when
the only alternative would create a sub-15-second image.

`touchdesigner/podcast_sequencer.py` is a provider-neutral, stateless playback
core. `/project1/podcast_visualizer` in the current local working revision,
`podcast.20.toe`, follows the TouchDesigner 2025.32820 timeline and exposes:

- `prompt_out` for one prompt or two smoothstep-weighted crossfade prompts;
- `caption_out` for the current spoken caption;
- `status_out` for playhead and scene diagnostics;
- `show_control` for live play, audio-source, seed, crossfade, and color controls;
- `color_out_1` and `color_out_2` for adjusted primary and backup images;
- `voices_only_audio` and `soundscape_audio`, both locked to the same timeline;
- `audiosource_switch`, which sends exactly one selected stem to `audio_out`.

The local `podcast.20.toe` contains the supplied primary and backup
StreamDiffusionTD components. The controller maps `prompt_out` into both
operators' weighted prompt and seed blocks and uses spherical interpolation
for scene crossfades. `Crossfade Seconds` defaults to 8 seconds, accepts values
up to 30 seconds, updates live, and is capped at half the current scene
duration. The final half of each loop blends toward scene one and the opening
half completes the same transition, so the visual loop has no hard boundary.
`Random Seeds Each Loop` switches between repeatable seed values and a fresh,
internally consistent seed bank for every loop. The Color tab adjusts
brightness, contrast, gamma, black level, opacity, hue, saturation, and value
through post-generation Level and HSV TOPs. Reinstalling the show-control
component preserves its current playback, seed, crossfade, and color values.
Only one model server should run at a time.
`Audio Source` offers only `Human Voices Only` and `Soundscape Only`; the
combined review mix is deliberately excluded. `Audio Enabled` gates the
selected stem at the Audio Device Out, and saved paused projects reopen at
frame 1 with audio disabled. See
[touchdesigner/README.md](touchdesigner/README.md) for the adapter boundary.
Brightness `1.0` is neutral in the Level TOP; `0.0` is black and values above
`1.0` brighten the image.

The local `.toe` and `.tox` files, including `podcast.20.toe`, are ignored by
Git and must not be published.

## Project layout

```text
config/       Controlled themes and show/host bible
contracts/    Machine-readable AI output contracts
data/         Rebuildable incremental catalog
episodes/     Locked manifests and publishable outputs
home_podcast/ Python pipeline
prompts/      Versioned editorial prompts
tests/        Deterministic tests
work/         Rebuildable provider jobs and intermediate files
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for state and immutability
rules and [docs/PILOT.md](docs/PILOT.md) for decisions needed before the first
voice-generation run.
