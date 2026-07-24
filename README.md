# Recovered Homes

Recovered Homes is an incremental production pipeline for a popular,
multi-host synthetic podcast about home, belonging, digital history, and
digital archaeology.

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
  → locked episode evidence packet
  → grounded multi-host script
  → cached segment-level speech jobs
  → normalized WAV + MP3
  → Markdown + WebVTT + SRT transcripts
```

Deterministic code owns parsing, WARC dates, IDs, history, manifests, caching,
audio assembly, and transcripts. AI providers are used only for semantic story
cards, scriptwriting/editorial passes, and synthetic speech.

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

Export only stories that do not have a current cached story card:

```powershell
python -m home_podcast export-analysis --month 2013-12
```

This creates:

```text
work/analysis/2013-12-story-jobs.jsonl
```

Each line contains one story, its provenance, the controlled theme vocabulary,
and the required result contract. The analysis model should follow
`prompts/story_analysis.md` and return JSONL shaped like:

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

Import cards only after validating the provider output:

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
python -m home_podcast plan --month 2013-12
```

The proposal uses all eligible stories, groups them by primary theme, and
splits large themes into parts based on `target_stories_per_installment`.
Stories are not silently discarded: the proposal reports assigned,
unanalyzed, and ineligible records separately.

The proposal is editorial input, not a published manifest. During the pilot,
lock the preferred installment before script generation:

```powershell
python -m home_podcast lock-episode `
  --proposal .\work\planning\2013-12-proposal.json `
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

Validate story coverage, speakers, citations, and exact quotations:

```powershell
python -m home_podcast validate-script `
  --script .\work\scripts\2013-12.01-script.json `
  --evidence .\work\scripts\2013-12.01-evidence.json
```

Validation fails if even one selected story has no traceable use.

## Speech, audio, and transcripts

After assigning stable voice IDs in `config/show_bible.json`, create one cached
speech job per speaking turn:

```powershell
python -m home_podcast prepare-tts `
  --script .\work\scripts\2013-12.01-script.json `
  --provider PROVIDER_NAME `
  --model MODEL_NAME
```

The chosen speech adapter consumes the JSONL jobs and writes WAV files to each
job's `output_audio` path. The cache key includes provider, model, voice, text,
delivery direction, and pronunciation settings, so only changed lines require
regeneration.

Once every clip exists:

```powershell
python -m home_podcast render-audio `
  --jobs .\work\tts\2013-12.01-jobs.jsonl
```

The renderer uses FFmpeg to normalize clips to 48 kHz stereo, insert scripted
pauses, target podcast loudness, and create a WAV master, MP3 distribution
copy, and exact segment timeline.

Generate deliverable transcripts:

```powershell
python -m home_podcast transcript `
  --timeline .\episodes\2013-12.01\audio\2013-12.01-timeline.json
```

Outputs include speaker-labeled Markdown, WebVTT, and SRT with a story-to-script
source map.

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
