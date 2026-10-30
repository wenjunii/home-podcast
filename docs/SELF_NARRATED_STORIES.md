# Self-narrated storytelling path

This is the active production direction for the recovered December 2013
stories. The rotating-host podcast remains preserved as a separate path and can
be resumed later without converting or overwriting its manifests, scripts,
audio, visual prompts, soundscapes, or TouchDesigner projects.

The current offline 3080 speech default is one continuous Qwen VoiceDesign take
per reviewed short story, followed by CPU speech checks and consistent-volume
mastering. Casting and delivery are frozen per story; original audio is retained.
See [the local production stages](LOCAL_AUDIO_3080.md#current-default-one-whole-story-voicedesign-take).
The former section-cloning runner remains an explicit legacy option, and the
5090 live workflow is unchanged.

## Creative format

Each eligible unique source story normally becomes one independently playable
performed adaptation. When a captured page contains separately attributable
first-person authors, deterministic editorial decisions split it into one
narration per voice. Index pages, dictionaries, quotation aggregators, and
other extraction false positives remain documented exclusions. There is no
host introduction or discussion. The language should
feel remembered and spoken: conversational phrasing, contractions, varied
rhythm, supported emotion, and room for breaths and silence. It is an
adaptation, not a word-for-word reading.

New narrations have a **five-minute (300-second) finished-audio maximum**,
including breaths, natural pauses and added tail silence. A short but meaningful
fragment remains short. Plan roughly 450–550 English words or fewer; final
duration is measured, not inferred from word count. The deterministic preflight
budgets 140 words per minute, explicit pauses and 15 seconds of performance
headroom. These are planning assumptions, not an instruction to speak faster.

Long sources and full adaptations remain intact. The user's current choice is
one condensed version per story, never multiple parts. Keep the central personal
arc, essential context and supported ending while condensing secondary details
and repetition. Exact omitted excerpts and reasons belong in
`editorial_omissions` as `duration_condensation`, not in speech. Every shortened
edition needs fresh evidence-backed review; length validation is not approval.
Never truncate audio, time-compress speech or invent closure. Existing long auditions and published artifacts are
preserved, and the separate podcast plan keeps its information-driven runtime.
Thematic labels create collections and playlists, but stories are not merged
into a composite autobiographical voice.

`target_minutes_max` in `storytelling.real-december.json` owns the production
limit. Local speech plans recheck the current text budget, including cached
legacy job files. Assembly checks exact WAV frames before replacing a master;
new live bundles check measured audio before promotion. An overrun is held,
leaving the previous master or live bundle unchanged. Historical audition
helpers under `work/` are experiments, not a bypass for new production.

### Single-short-edition audit

Run the no-network duration inventory with:

```powershell
py -3.10 -m scripts.audit_storytelling_duration --config .\storytelling.real-december.json
```

This writes `work/storytelling-real-december/condensation/collection-duration-audit.json`
and `pending-condensation-jobs.jsonl`. It does not write narrations, select
sentences mechanically, approve stories, split stories or generate audio.
The queue binds each draft and frozen source job by content hash. Read those
complete artifacts and author each condensed adaptation in the active Codex
task. Then import through `import-storytelling` and perform a fresh individual
personal-story review. `condensation` metadata identifies the prior full
adaptation; the importer preserves it and its review under the story's
`full-editions/<hash>/` directory before replacing an unpublished draft.
Published artifacts and frozen source jobs remain immutable.

October 28 status after the first short-edition revision: all 415 drafts were
screened, 213 fit the text budget and 202 still need condensation. All 10
editorially approved personal stories fit the text budget, including the
482-word single edition of *An Outsider on the Inside* (about 3:45 estimated,
including explicit pauses and headroom). The other 405 drafts still need
individual personal-story review or rewriting; duration checks do not clear
that queue. No new audio has been rendered for the condensed edition. Its six
sections are performance beats within one story, not separate story parts.

## Perspective and identity

“Self-narrated” describes the intimate storytelling form, not a claim that the
generated performance belongs to the original writer or witness.

- Use first person when the recovered text clearly establishes its own
  first-person narrator.
- Use attributed first person for clearly attributed testimony.
- Hold a story outside the narrated collection when the evidence cannot safely
  establish who may say “I.” There is no third-person fallback.
- Never create a fictional person merely to make an uncertain fragment say
  “I.”
- Never merge independently signed contributors, a post and its reblog reply,
  or bilingual family members into one first-person identity. Record a source
  partition and retain the shared source story ID and content hash.

Gender presentation, accent, age presentation, and personality are separate
casting dimensions. Explicit evidence may constrain a voice trait, but a name,
language, URL, nationality reference, or story location never establishes a
person's race, ethnicity, gender, age, religion, or accent. Unsupported voice
traits are documented as artistic casting and never as source identity.

For a human provider voice, an accent must come from the auditioned speaker's
verified natural speech. For a locally designed synthetic voice, an accent is
an auditioned presentation: reject caricature, unstable pronunciation, or
stereotyped performance. The system does not request imitation of a real
person, and sharing a geographic label is never sufficient reason to match a
voice to a story.

## Per-story artifacts

Each supported first-person narration gets its own immutable directory:

```text
narrations/real-december/<narration-id>/
  manifest.json
  source-job.json
  adaptation.json
  cast.json
  audio/
    <narration-id>-voices-only.wav
    <narration-id>-voices-only.mp3
    <narration-id>-timeline.json
  transcripts/
    <narration-id>.md
    <narration-id>.vtt
    <narration-id>.srt
  provenance.json
```

Optional soundscape and visual artifacts can be added later without changing
the voices-only master.

## Incremental model

The stable story ID and content hash define a narration source version.

- An unchanged story with a completed adaptation and frozen cast is skipped.
- A changed, unpublished story creates a new adaptation job for its new content
  hash.
- A published narration is immutable. Late or corrected evidence becomes a
  revision or supplement rather than silently replacing it.
- Provider speech is cached per adaptation section and voice/performance hash.
- Transcript and caption timing derives from the rendered voice timeline.

## Local adaptation workflow

The first four production gates are implemented and make no provider calls.
Create the immutable one-story-per-narration plan and export only adaptations
that are not already complete:

```powershell
py -3.10 -m home_podcast `
  --config .\storytelling.real-december.json `
  plan-storytelling `
  --month 2013-12

py -3.10 -m home_podcast `
  --config .\storytelling.real-december.json `
  export-storytelling `
  --plan .\work\storytelling-real-december\planning\2013-12-storytelling-plan.json
```

Each JSONL job contains the complete recovered source, its full enrichment
card, perspective evidence, completeness status, and every enrichment excerpt
that the adaptation must account for. The plan requires supported first person
whenever the source establishes an “I” or “we.” Sources without that evidence
remain explicitly held rather than being converted to third person or
fictional first person.

Author one result object per job directly in Codex, following
`prompts/storytelling_writer.md`, and save the batch as, for example:

```text
work/storytelling-real-december/adaptations/2013-12-results.jsonl
```

Then validate and import it through the deterministic gate:

```powershell
py -3.10 -m home_podcast `
  --config .\storytelling.real-december.json `
  import-storytelling `
  --input .\work\storytelling-real-december\adaptations\2013-12-results.jsonl `
  --jobs .\work\storytelling-real-december\adaptations\2013-12-jobs.jsonl
```

Running `export-storytelling` again skips every unchanged valid adaptation, so
new or corrected source records do not restart the collection. To inspect one
adaptation against the complete jobs file:

```powershell
py -3.10 -m home_podcast `
  --config .\storytelling.real-december.json `
  validate-storytelling `
  --adaptation .\narrations\real-december\<narration-id>\adaptation.json `
  --job .\narrations\real-december\<narration-id>\source-job.json
```

December 2013 has 415 structurally valid imported drafts. The personal-story
re-audit approved 9, corrected 6 of those, and blocked 406 for further editorial
work. Zero missing imports is not zero pending editorial review. The earlier
15 false-positive exclusions and three multi-narrator splits are
versioned in `series/2013-12/storytelling-editorial-decisions.json`. Audit the
whole collection after regenerating an `--include-existing` jobs file:

```powershell
py -3.10 -m scripts.audit_storytelling_collection `
  --config .\storytelling.real-december.json `
  --jobs .\work\storytelling-real-december\adaptations\2013-12-all-current-jobs.jsonl `
  --report .\work\storytelling-real-december\adaptations\2013-12-collection-audit.json
```

The pre-ElevenLabs gate removes raw links, addresses, HTML, archive reply
syntax, deterministic page residue, and recoverable character-encoding damage
from spoken text without changing source evidence. It then creates a canonical
production index, an editorial audit, and one provider-neutral inventory row
per spoken section:

```powershell
py -3.10 .\scripts\clean_storytelling_for_speech.py `
  --config .\storytelling.real-december.json `
  --jobs .\work\storytelling-real-december\adaptations\2013-12-all-current-jobs.jsonl `
  --backup-root .\work\storytelling-real-december\pre-elevenlabs\original-adaptations `
  --report .\work\storytelling-real-december\pre-elevenlabs\2013-12-speech-cleanup-report.json

py -3.10 .\scripts\build_storytelling_preflight.py `
  --config .\storytelling.real-december.json `
  --jobs .\work\storytelling-real-december\adaptations\2013-12-all-current-jobs.jsonl `
  --index .\series\2013-12\storytelling-production-index.json `
  --audit .\work\storytelling-real-december\pre-elevenlabs\2013-12-editorial-audit.json `
  --inventory .\work\storytelling-real-december\pre-elevenlabs\2013-12-section-inventory.jsonl
```

Omit `--execute` from the cleanup command for the normal audit-only pass. If
cleanup is required, inspect the report and rerun with `--execute`; the command
refuses published manifests and stores the first recoverable copy under the
backup root. Structural validation alone does not authorize even an audition.
The production preflight additionally requires a current evidence-backed
`personal-story-review.json`. It blocks source commentary, navigation,
archive-month lists, sales copy, and the 349 remaining conservative source
copies. Heuristics never grant editorial approval. Source-explicit personal
memories must be reviewed in full, with attribution and recovery gaps kept out
of speech. See [the audit](PERSONAL_STORY_CONTENT_AUDIT.md).
The frozen counts, artifact pointers, and zero-call execution record are in
`series/2013-12/pre-elevenlabs-handoff.json`.

After auditioned voices have been added to
`config/storytelling_voice_policy.json`, freeze a matching narrator with:

```powershell
py -3.10 -m home_podcast `
  --config .\storytelling.real-december.json `
  cast-storytelling `
  --narration <narration-id>
```

The remaining content gate covers 406 drafts, including 349 conservative copies;
these must be personally reviewed and rewritten or held, not bulk-approved.
The local initial-audio implementation now provides a representative synthetic
voice audition, reviewed local roster, frozen per-story cast, resumable
section-level Qwen rendering, voices-only assembly, timelines, captions, and
continuous Stable Audio 3 soundscapes. Every executed local phase begins with
an exact dry-run call ceiling; no paid API is involved. See
[`LOCAL_AUDIO_3080.md`](LOCAL_AUDIO_3080.md). The ElevenLabs path remains
preserved as an optional quality fallback.

## Optional live local variations

Canonical Codex adaptations and initial ElevenLabs renders remain immutable
fallbacks. The optional 5090 path can prepare another rendition while the
current story plays:

```text
canonical adaptation + source evidence + casting policy
  -> seeded interpretive casting card
  -> constrained Gemma 4 12B first-person variation
  -> deterministic evidence and structure gate
  -> local Qwen3-TTS render and section timing
  -> casting-aware 68–75-token SDXL prompt variations
  -> validated next-loop bundle
```

The 3080-safe profile does not import or load either local model. The 5090
profile is opt-in and uses the file protocol under
`work/storytelling-real-december/runtime`. See
[`LIVE_LOCAL_VARIATIONS.md`](LIVE_LOCAL_VARIATIONS.md) for setup, commands,
fallback behavior, and TouchDesigner controls.
