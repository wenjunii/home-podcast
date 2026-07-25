# Recovered Homes

Recovered Homes is an incremental production pipeline for a popular,
rotating-cast podcast about home, belonging, digital history, and digital
archaeology.

The source corpus lives in the sibling extractor project. This project reads
only `stories_*.md` files and deliberately ignores `matches` exports and the
compressed JSONL export.

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
audio assembly, and transcripts. AI providers are used only for semantic story
cards, scriptwriting/editorial passes, and voice performance.

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
../cc-home-extractor/data/exports
```

Change `exports_dir` in `podcast.json` if the extractor moves.

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

The configured analysis and script model is Capriole Fable 5. Supply its
credential only through the process environment:

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

The current speech-provider shortlist and pilot audition recommendation are in
[docs/SPEECH_PROVIDERS.md](docs/SPEECH_PROVIDERS.md).
The selected one-theme pilot and its TTS cost model are in
[docs/PILOT_EPISODE.md](docs/PILOT_EPISODE.md).

Non-voice audio is an independent layer. The pilot contains one nearly
subliminal full-episode base bed, seven long thematic beds, and five structural
or spot cues. They are illustrative sounds, not simulated historical
recordings. Validate them and prepare provider-neutral generation jobs:

```powershell
python -m home_podcast validate-sound-design `
  --sound-design .\episodes\2013-12.01\sound-design.json `
  --script .\episodes\2013-12.01\script.json

python -m home_podcast prepare-sfx `
  --sound-design .\episodes\2013-12.01\sound-design.json `
  --script .\episodes\2013-12.01\script.json `
  --provider elevenlabs `
  --model eleven_text_to_sound_v2

# Dry run: no credential and no provider call
python -m home_podcast generate-sfx `
  --jobs .\work\sfx\2013-12.01-jobs.jsonl
```

The cue contract, provider research, provenance policy, and mixing behavior are
documented in [docs/SOUND_DESIGN.md](docs/SOUND_DESIGN.md).
Paid generation is opt-in and requires both `--execute` and an explicit
`--max-credits` ceiling. Provider keys are read only from environment
variables and must never be committed.

Once every speech and generated-effect clip exists:

```powershell
python -m home_podcast render-audio `
  --jobs .\work\tts\2013-12.01-jobs.jsonl `
  --sound-design .\episodes\2013-12.01\sound-design.json `
  --sfx-jobs .\work\sfx\2013-12.01-jobs.jsonl
```

The renderer uses FFmpeg to normalize clips to 48 kHz stereo, insert scripted
pauses, extend each thematic bed to the next eligible handoff, suppress
too-short handoffs, place and fade structural cues, and create synchronized
192 kbps deliverables:

- `<episode>-voices-only.mp3`
- `<episode>-soundscape-only.mp3`
- `<episode>.mp3` as a combined review mix

The non-human stem is continuous because a quiet base loop covers any interval
without a retained thematic bed. Omitting the two sound-design arguments still
produces the voices-only render.

Generate deliverable transcripts:

```powershell
python -m home_podcast transcript `
  --timeline .\episodes\2013-12.01\audio\2013-12.01-timeline.json
```

Outputs include speaker-labeled Markdown, WebVTT, and SRT with accessible
non-speech labels, the sound-design disclosure, and a story-to-script source
map.

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
