# Recovered Homes

Recovered Homes is an incremental production pipeline for stories about home,
belonging, digital history, and digital archaeology. The active production path
is now one conversational self-narrated adaptation per archived story. The
existing rotating-cast podcast path remains preserved and can be resumed later.

The canonical source snapshot is tracked in `data/exports`. It contains only
`stories_*.md` files copied from the sibling extractor project and deliberately
excludes `matches` exports and the compressed JSONL export.

The current tracked snapshot contains 1,652 unique stories in ten languages:
677 captured in May 2013, 444 in December 2013, 281 in March 2014, 180 in
April 2014, and 70 in July 2014. Capture time is provenance from the WARC
filename, not a claim about writing or publication time. Ninety-one stories
currently have portable analysis cards; the remaining 1,561 stay available for
incremental Codex analysis.

The system is designed around three promises:

1. New or changed stories are processed incrementally.
2. Every spoken claim remains traceable to archived source evidence.
3. Published narrations and podcast episodes remain reproducible even when
   older crawl months receive late-arriving stories.

## Active self-narrated storytelling path

### Local-first operation; GitHub optional

Use `python -m scripts.private_handoff` to plan, export, verify and import a
private dependency-complete snapshot of the current 136-story `.40` edition.
The default includes approved individual story audio, frozen sources,
adaptations and approval receipts as well as the complete playback show.
Content-addressed snapshots reuse unchanged files; imports never overwrite
different existing files or an existing 5090 setup. No GitHub, paid API,
media generation or Git commit is involved.

Keep the package private: it contains the selected licensed TOE and personal
story material, not model weights, environments, credentials or Git history.
GitHub remains available for optional code-only publishing; nothing is pushed
automatically. See [private cross-PC export/import and TouchDesigner rebinding](docs/PORTABLE_SETUP.md#current-local-first-handoff-136-stories--podcast40toe).
Before an explicitly requested public sync, run
`python -m scripts.check_public_sync` on staged files, then
`python -m scripts.check_public_sync --base origin/main` on the new commits.
The gate checks Git blobs for private assets and recognizable credentials;
neither command pushes or publishes anything.

### Current local 136-story continuous-image edition (.40)

Open **`podcast.40.toe`** in TouchDesigner **2025.32820** on the RTX 3080.
The outgoing approved scene now continues through uncovered visual intervals,
the one-second story separators and the loop tail. It interpolates into the
next scene only at that scene's unchanged approved cue. Mid-story colour
interruptions are disabled; Show Control's legacy gap-colour control is greyed
out at zero. A held scene is a presentation reference, not an extension of its
source event.

**Scene Interpolation Seconds** and **Story / Loop Interpolation Seconds**
remain adjustable, both defaulting to **3**, capped at half the incoming scene.
The 136 stories, 619 scenes per path, 2,862 captions, three audio modes and
3:18:58.720 clock are unchanged. Interpolation blends prompt and seed weights
(`slerp`), not buffered rendered frames. Live renderer motion still needs a
visual check with only your selected StreamDiffusionTD server running.

`.38`, every earlier project, all reviewed media and the 5090 setup are
preserved. Isolated build and native reopen/output/control audit receipts:
`work/storytelling-real-december/continuous-image-hold-136-3080-2026-10-30/`.

### Preserved local 136-story interpolation edition (.38)

Open **`podcast.38.toe`** in TouchDesigner **2025.32820** on the RTX 3080.
All three visual paths now interpolate at every within-story join, story
boundary and full-playlist loop. **Scene Interpolation Seconds** and
**Story / Loop Interpolation Seconds** both default to **3**; the requested
duration is capped at half the incoming scene. Zero explicitly disables it.
Incoming prompt weight starts at zero at its approved cue, never before it.
The outgoing image is a temporary transition reference, not an extension of
its event or a claim that two narrators share an identity.

**Gap Colour Fade Seconds** now handles actual uncovered visual gaps only;
it is not a substitute for story or loop interpolation. Interpolation blends
prompt and seed weights (`slerp`); generated-image motion remains dependent on
the renderer, not a guaranteed linear dissolve between two rendered buffers.
The 3080 adapter also deterministically folds unsigned32-bit canonical seeds
into TD's supported positive integer range. This prevents a seed overflow
from aborting a blend halfway through its parameter update. Saved canonical
seeds are unchanged, and random/stable seed modes remain available.

The same 136 stories, 619 scenes per path, 2,862 captions, approved audio and
one-second separators are reused without regeneration. `.36`, every older
project, all source media and the 5090 setup are preserved. Start only one
StreamDiffusionTD server yourself. Build and audit receipts are in
`work/storytelling-real-december/interpolated-136-3080-2026-10-30/`.

### Preserved local 136-story five-second edition (.36)

Open `podcast.36.toe` in TouchDesigner **2025.32820** on the RTX 3080.
It contains the current **136 approved stories / 3:18:58.720**, including
the 24 newly approved richer ambient revisions and 112 unchanged soundscapes.
All three audio modes have exact one-second silent separators between stories
and at the loop tail; narration, approved mix levels and caption wording are
unchanged. The three visual paths each contain **619 approved scenes**, with a
five-second minimum and a source-grounded opening prompt at every story start.
All paths share the same 2,862 captions and audio clock.

Show Control → Playlist provides **Story / Loop Transition Seconds** (0–30)
and **Soft Colour Transition Seconds** (0–5). The within-story scene crossfade
remains independent. Expired memory images fade into soft abstract colour,
not black or another person's memory; incoming prompts never run before their
story starts. Story transitions default to zero seconds for immediate incoming
prompt changes; increase the control for a colour-mediated reveal. Generated
images still have renderer response latency. Playback starts paused, with
Balanced Memories and Narration + Ambient selected. Start only one
StreamDiffusionTD server yourself; installation and tests do not start either.
The 5090 setup, `.34`, `.28`, all older projects and source media are preserved.
The seven excluded stories and 204 later recordings remain outside this build.

The edition manifest, approval bindings, isolated installer and validation
receipts are in
`work/storytelling-real-december/approved-136-five-second-3080-2026-10-30/`.
See [the .36 controls and verification notes](touchdesigner/README.md#current-offline-136-story-edition-36).

### Preserved 45-story edition (.28)

The preserved local RTX 3080 storytelling playlist is `podcast.28.toe`
(TouchDesigner 2025.32820), with **45 approved stories / 55:35.680** on one
shared audio, caption and visual clock. In Show Control, Audio Source now
offers **Narration Only**, **Ambient Only**, and **Narration + Ambient**.
The combined mix retains the approved voice level and existing background-bed
level with a safety limiter; it does not generate new audio. Solo source
recordings are preserved. Playlist controls add **Jump to Story**, **Previous
Story**, **Next Story**, **Restart Playlist**, **Loop Full Playlist**, current
story/time displays, and adjustable **Story Edge Fade Seconds**. Story joins
and the full loop fade through black, never preloading the next person's
memory into the outgoing image. The visual scene Crossfade Seconds control
still works independently. Playback is initially paused with combined audio
and Balanced Memories selected; live generation is locked off for this offline
3080 collection. Start only the StreamDiffusionTD version you intend to use.
See [`touchdesigner/README.md`](touchdesigner/README.md#full-offline-storytelling-playlist-28)
for build, installation and audit commands. This is the preserved 45-story
approved subset, not the entire December source collection. Visual renders
still need editorial review; no model server is started by setup or audits.
The previous `.26` retains its original 35-story / 40:56.240 collection.
The new edition has 818 unchanged captions and **166 source-detail scenes per
visual path** (498 prompt treatments). Contextual, Human Figures and Balanced
Memories now share the same speech-anchored memory beats. The user-approved
revision adds concrete story objects, actions and settings and corrects three
early openings, with 15-second minimum holds and post-onset crossfades.
Its ten appended stories occupy slots 36–45. `.27` preserves the previous
132/132/161-scene edition; all source audio, earlier prompts and cached segments
remain intact. No narration or ambient audio was regenerated for `.28`.

The preserved smaller RTX 3080 storytelling test is `podcast.25.toe` (TouchDesigner
2025.32820), saved separately from `.24`, `.23` and the preserved podcast projects.
Show Control → Visual Path offers **Balanced Memories**, **Original Story
Visuals**, and **Human Figures**. Balanced Memories has 124 newly authored
scenes for the current 35 audio/caption-approved stories, compared with 95 in
each retained path. It mixes people, interactions, places, actions and object
details on the unchanged voice/ambient clock; scene changes follow recorded
speech anchors and every image lasts at least 15 seconds. The `.25` test story
selector still covers stories 1, 5 and 28, not the entire December collection.
The `.25` revision rewrites all 124 balanced prompts to prioritize source
objects, actions, relationships and settings over generic mood wording. Hand
Library and the grandparents' riverside picnic have their own speech-anchored
images; the audio and caption clocks remain unchanged. Review all 35 prompt
sequences, including the previous balanced edition for comparison, in
`audio/storytelling-real-december/rich-visual-review-2026-10-29/index.html`.
Prompt validation is complete; actual generated images still need editorial
review. No model server is started by the setup or routing audits.

The December 2013 collection is configured separately in
`storytelling.real-december.json`. It shares the recovered source catalog and
analysis cards but writes to dedicated `narrations/`, `work/`, and `audio/`
directories. Each eligible unique story becomes one conversational spoken-word
adaptation with a frozen, evidence-aware narrator. New story narrations have a
**five-minute maximum**, including breaths, pauses and tail silence; shorter
stories are not padded. Each longer story receives one condensed version, not
parts; the full source and previous adaptation stay intact. The podcast path's
information-driven runtime policy is unchanged.

Local narration playback now uses the shared settings in
[`config/speech_mastering.json`](config/speech_mastering.json): a common speech
level, gradual volume-drift correction, and peak headroom. Original takes and
caption timing are preserved. This CPU-only finishing step does not make another
TTS call; changing the settings creates a new cached listening master. See
[speech-level setup](docs/LOCAL_AUDIO_3080.md#consistent-speech-volume).

The next ten-story narration batch is listening-approved at
`audio/storytelling-real-december/production-batch-03-2026-10-29/index.html`
(14:39.440 total; each complete take is under five minutes). It includes
level-controlled WAVs, exact narration transcripts, and 306 draft audio-timed
caption cues in SRT/VTT. Two recognition errors were resolved only after the
user checked short excerpts and independent unprompted recognition agreed;
the original recordings and ASR reports are preserved. The user's full-batch
listening approval is recorded separately from caption editorial approval.

Its ten continuous soundscapes are also listening-approved at
`audio/storytelling-real-december/ambient-production-batch-04-audible-v2-2026-10-29/index.html`.
Each story has an unchanged approved voice player, a voice-plus-ambient preview,
and a matched-level ambient-only preview. Two new effects were generated on
local CUDA; an additional short background candidate was preserved but excluded
because it faded too early. The corrected edition reuses a tested longer room-air
texture, with no replacement generation or relaxed level limits. Approval is
recorded in a separate hash-bound sidecar; historical manifests are unchanged.

The new ten-story caption edition is also approved, and remains available at
`audio/storytelling-real-december/caption-review-10-readable-v2-2026-10-29/index.html`:
216 audio-timed cues, SRT/VTT and a spoken transcript for each story. All 24
recognition/script discrepancies were reviewed individually with source spelling
evidence and 15 offline unprompted clip checks. Three apparent spoken variations
are retained; nine wording/repetition checks remain visible in the historical
review page. The user's overall caption acceptance is recorded in a separate
sidecar and does not authorize any voice repair. The readability revision keeps
supported names together and improves phrase breaks without changing caption
text or any audio. Original 306-cue drafts
and the first 215-cue editorial edition are preserved.

The next ten stories have three prompt-approved visual paths at
`audio/storytelling-real-december/visual-review-next-10-2026-10-29/index.html`:
37 memory scenes and 111 distinct contextual, human-figure and balanced prompt
treatments. All prompts are 71–75 SDXL content tokens, all human-path scenes
request safe front-facing portraits, and all paths use the approved 14:39.440
audio/caption clock. Locations and source-specific details have exact evidence;
future wishes remain distinct from completed memories. The page supports path
switching, four unchanged audio choices and post-onset fade preview. No image
model is started. Prompt approval is recorded in a hash-bound sidecar; these
stories are now included in `.27`. Actual generated-image review remains
separate. `.26` still retains the previous 35-story approved collection. See
[batch 04 production notes](docs/LOCAL_AUDIO_3080.md#ambient-batch-04-for-the-next-ten-stories).
See also [next-ten visual production](docs/LOCAL_AUDIO_3080.md#three-visual-paths-for-the-next-ten-stories).

Voice gender presentation, reviewed accent presentation, personality, and emotional
range rotate across stories. They are constrained by identity evidence only
when the source explicitly supports that constraint; otherwise they remain
documented artistic casting choices rather than claims about the source person.

The format, safeguards, artifacts, and next engineering gates are documented in
[`docs/SELF_NARRATED_STORIES.md`](docs/SELF_NARRATED_STORIES.md). The editorial
rules are in `config/storytelling_bible.json`, and new adaptations must conform
to `contracts/storytelling-script.schema.json`.

Build or refresh the December narration plan and its pending Codex jobs without
making a network or paid API call:

```powershell
py -3.10 -m home_podcast `
  --config .\storytelling.real-december.json `
  plan-storytelling --month 2013-12
py -3.10 -m home_podcast `
  --config .\storytelling.real-december.json `
  export-storytelling `
  --plan .\work\storytelling-real-december\planning\2013-12-storytelling-plan.json
```

The December collection contains 415 structurally valid narration drafts
representing 412 source-story pages. Structural validity is not personal-story
approval. Following the October 28 source-backed short-edition reviews, **367
personal stories are approved and 48 remain held**. The earlier initial audit
had approved only 9 and blocked 406; those historical counts are not the current
production queue. The Warm Atlantic lyric source remains held rather than
treated as autobiography.
The old roughly 60-hour estimate includes unapproved source copies and must not
be used as a production runtime. See
[`docs/PERSONAL_STORY_CONTENT_AUDIT.md`](docs/PERSONAL_STORY_CONTENT_AUDIT.md).
Three pages with two distinct
source voices were split into six independently attributed narrations. Two
otherwise eligible records remain outside the collection because their text
does not safely establish who may say “I”, and 15 extraction false positives
are explicitly excluded. The decisions are recorded in
`series/2013-12/storytelling-editorial-decisions.json`. Export remains resumable;
zero missing structural adaptations does **not** mean zero pending editorial
work. The personal-story review queue is separate and remains visible.

Re-export all current jobs and audit every canonical adaptation, locked source
job, and manifest without a network call:

```powershell
py -3.10 -m home_podcast `
  --config .\storytelling.real-december.json `
  export-storytelling `
  --plan .\work\storytelling-real-december\planning\2013-12-storytelling-plan.json `
  --output .\work\storytelling-real-december\adaptations\2013-12-all-current-jobs.jsonl `
  --include-existing
py -3.10 -m scripts.audit_storytelling_collection `
  --config .\storytelling.real-december.json `
  --jobs .\work\storytelling-real-december\adaptations\2013-12-all-current-jobs.jsonl
```

Before any speech-provider work, run the no-network cleanup check and rebuild
the provider-neutral production inventory:

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

The inventory now includes only current, evidence-backed personal-story
approvals. The 48 held records include 35 still flagged as conservative copies;
an authored label is not approval either. A `personal-story-review.json` sidecar
binds each approval to the exact adaptation and frozen source job. Old cached
plans cannot bypass this gate. No candidate voice IDs or casts are invented
before the storytelling-specific audition.

```powershell
py -3.10 -m scripts.audit_personal_story_content --config storytelling.real-december.json
```
The machine-readable stopping point is
`series/2013-12/pre-elevenlabs-handoff.json`.

The initial audio path now has two alternatives: the preserved ElevenLabs
workflow and a resumable local 3080 workflow. The default local speech path now
uses **one continuous Qwen VoiceDesign take per reviewed story**, with frozen
casting, emotional direction and natural pauses. CPU speech checks, shared
volume leveling and audio-timed draft captions follow; raw takes stay intact.
The earlier Base section-cloning workflow remains an explicit legacy option.
Stable Audio soundscapes are a separate, later production phase.
It does not load models while TouchDesigner is running and does not modify the
3080 or 5090 `.toe` projects. Setup, exact dry-run ceilings, bounded batches,
hash-bound listening approvals and production commands are in
[`docs/LOCAL_AUDIO_3080.md`](docs/LOCAL_AUDIO_3080.md).

The first ten-story audio batch and second 25-story batch are listening-approved. The second batch has
25 new complete takes (27:12 total), with transcripts and audio-timed draft
SRT/VTT captions at the local
`audio/storytelling-real-december/production-batch-02-2026-10-28/index.html`.
All 25 pass technical checks and are under five minutes; caption-editorial
approval is still pending. No earlier assets were replaced.

A three-story ambient audition now tests local GPU sound generation on this
3080 Ti. Listen at
`audio/storytelling-real-december/ambient-audition-2026-10-28/audible-v3/index.html`
for complete ambient stems and mixes with the approved narration. Six source
assets rendered in 20.307 seconds after model loading, with CUDA execution
verified. The new listening edition replaces the bass-heavy house room tone
and applies the shared `config/ambient_mastering.json` standard: -24 LUFS source
sounds, -30 LUFS production backgrounds, and -23 LUFS solo previews. Finished
backgrounds measure within 0.1 LU of the same target; originals are preserved.
Future local ambient jobs use the same loudness and audibility gates. Ambient
listening approval remains pending. See the
[GPU ambient audition](docs/LOCAL_AUDIO_3080.md#gpu-ambient-audition-on-the-3080-ti)
for the pinned runtime, evidence, timing and resumable trial commands.

The supported offline CUDA batch path is now `ambient-batch` (also available
through the 3080 PowerShell runner). The first production ambient batch covers
the ten listening-approved narrations from speech batch 01, totaling 13:44.72.
It uses 17 source-grounded sound assets; two effects whose post-mention spans
were under 15 seconds inherit the continuous background. The three-story
`audible-v3` audition is recorded as user-approved separately; this new batch
requires its own listening approval. Existing voices, podcast files, and 5090
settings are preserved. See [ambient batch production](docs/LOCAL_AUDIO_3080.md#resumable-gpu-ambient-batches).

For the current batch review, use
`audio/storytelling-real-december/ambient-production-batch-01-2026-10-28/volume-v2/index.html`.
Only story 10, **Allowed Home, but Unable to Stay**, has changed: its bass-heavy
background and quiet loop join are replaced by a previously approved,
non-locating air texture. Its solo preview measures -23 LUFS; the other nine
stories and every narration remain byte-identical. The edition uses no new
generation. The user approved story 10's repaired ambient-only track; this is
not bulk approval of the other nine soundscapes, combined mixes or captions.
New ambient batch plans also
freeze `config/ambient_audibility.json`, adding 250–8000 Hz energy, mono
compatibility and loop-dip checks alongside the existing loudness targets.

The next ten-story ambient listening package is
`audio/storytelling-real-december/ambient-production-batch-02-audible-v2-2026-10-28/index.html`
(10:15.52). It keeps the approved speech from narration batch 02 unchanged and
offers ambient-only, voice-only and combined previews. Thirteen source sounds
were generated locally on the 3080; the new gate held one bass-heavy apartment
take. The corrected edition uses the other twelve assets, sharing a passing
generic house-air texture across two suitable stories, with no further model
calls. Solo previews measure -23.07 to -23.00 LUFS; production backgrounds
-30.05 to -29.94 LUFS. The user has approved these ten soundscapes; captions
retain their separate pending editorial status. Approval is recorded under
`work/storytelling-real-december/local-audio/approvals/ambient-production-batch-02-audible-v2-2026-10-28.json`.
The final twelve stories in this approved speech queue are now prepared in
`audio/storytelling-real-december/ambient-production-batch-03-audible-v4-2026-10-28/index.html`
(14:28.72), with separate ambient stems and listening previews. Four weak
candidate backgrounds are preserved but excluded; corrected cached textures
need no replacement generation. The new edition also uses versioned peak-safe
solo mastering and repairs an interior fade gap in the final story. All twelve
need listening approval. This completes ambient preparation for the current
35-narration queue, not the entire December collection; caption review remains
separate. The three already-approved audition stories are not regenerated.

The optional live path keeps every canonical Codex adaptation and initial
render as an immutable fallback. `3080_safe` plays only those assets and leaves
local language and speech models unloaded. `5090_live` can
prepare a future loop with constrained Gemma 4 12B narration, a shared
interpretive casting card, Qwen3-TTS speech, and casting-aware SDXL prompts.
Nothing is promoted until the requested bundle validates and its audio exists.
See [`docs/LIVE_LOCAL_VARIATIONS.md`](docs/LIVE_LOCAL_VARIATIONS.md).

## Preserved podcast pipeline

The podcast plan and all existing pilot, audio, soundscape, visual,
TouchDesigner, episode, and configuration artifacts remain unchanged:

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

The requested Codex model for story analysis, first-person writing (initial
adaptations and revisions), and visual prompt writing is **GPT-6.1 Sol with
Extra High reasoning** (`gpt-6.1-sol`, `xhigh`). Select it in this conversation's
model controls; this repository preference does not change the running chat model. Existing
artifacts retain their original provenance. The local Gemma variation model
and speech, ambience, and image-generation models keep their separate roles.

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

This makes the preserved public-source/pilot snapshot self-contained, not the
current private storytelling show. To move the current show without GitHub,
use the private handoff above. To move the older public snapshot to another
computer, including rebuilding the local catalog and restoring cached story
analysis, follow [`docs/PORTABLE_SETUP.md`](docs/PORTABLE_SETUP.md).

Running `ingest` repeatedly is safe. Unchanged stories retain their catalog
records and cached analysis. Changed stories create a new version. Stories no
longer present in an export are marked missing rather than deleted.

To refresh from a sibling `cc-home-extractor` checkout, inspect the exact
stories-only change first and then apply it:

```powershell
python .\scripts\sync_story_exports.py
python .\scripts\sync_story_exports.py --apply
python -m home_podcast ingest
python -m home_podcast status
python -m home_podcast export-cards `
  --output .\data\story_cards\current-cards.jsonl
```

The synchronizer parses and verifies the complete source snapshot before
copying. It accepts only `stories_*.md`, reports story/content changes, never
copies `matches*` or compressed exports, and requires an explicit `--prune`
when a destination story file would be removed.

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

## Real December 2013 series

The pilot remains frozen. The production December series has its own config,
catalog, work directory, episode tree, and audio tree:

```text
podcast.real-december.json
series/2013-12/collection.json
data/full_exports/2013-12/
episodes/real-december/
work/real-december/
audio/real-december/
```

The series is information-driven: it has no 30-minute cap and no fixed story
count per installment. The initial deterministic proposal creates one populated
installment per theme and assigns every eligible story. If a theme contains
several natural subthemes, editorial planning may split it while preserving
complete coverage and stable source IDs. A proposal cannot be locked while any
current story remains unanalyzed.

First recover the complete captured sources in the sibling extractor. Always
review its no-network plan before a batch:

```powershell
Set-Location ..\cc-home-extractor
.\scripts\stories.ps1 -Action full-plan -Month 2013-12 -All
.\scripts\stories.ps1 -Action full-recover -Month 2013-12 -Limit 10 -Workers 3 -Apply
.\scripts\stories.ps1 -Action full-status -Month 2013-12 -All
.\scripts\stories.ps1 -Action full-export -Month 2013-12
```

The current dry plan covers 444 normal exported story units represented by 422
canonical captures, with an exact maximum of 844 Common Crawl requests. Recovery
is resumable. It never uses a generative model to finish missing text and labels
truncated, gated, or uncertain narratives explicitly.

After the extractor export exists, dry-run and apply the stories-only handoff:

```powershell
Set-Location ..\home-podcast
python .\scripts\sync_story_exports.py `
  --source ..\cc-home-extractor\data\full_exports\2013-12 `
  --destination .\data\full_exports\2013-12
python .\scripts\sync_story_exports.py `
  --source ..\cc-home-extractor\data\full_exports\2013-12 `
  --destination .\data\full_exports\2013-12 `
  --apply
python -m home_podcast --config .\podcast.real-december.json ingest
python -m home_podcast --config .\podcast.real-december.json status --month 2013-12
python -m home_podcast --config .\podcast.real-december.json export-analysis `
  --month 2013-12 `
  --output .\work\real-december\analysis\2013-12-jobs.jsonl
```

Codex then writes the new cards directly and imports them through the existing
validator. These full-source cards are evidence dossiers: ordered narrative
beats, usable factual details, people and explicitly supported identity details,
physical story locations, time markers, sensory details, exact excerpts, and
unresolved gaps. The later script packet includes the full source text for each
section; the card helps navigate it but does not limit the available facts.

Once all current sources are analyzed:

```powershell
python -m home_podcast --config .\podcast.real-december.json plan `
  --month 2013-12 `
  --information-driven `
  --output .\work\real-december\planning\2013-12-proposal.json
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
in `cohorts/2013-12-analyzed-pool.json`. The immutable
`cohorts/2013-12-full-corpus.json` records the 421-story corpus available when
the pilot was locked. The current exports contain 444 December stories; the 23
late discoveries belong in a supplement or later episode rather than changing
the published pilot manifest.

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

The pilot also has an interchangeable human-figure visual path at
`episodes/2013-12.01/visuals/2013-12.01-visual-scenes-human-figures.json`.
It preserves all 90 original scene IDs, boundaries, captions, story IDs,
locations, actions, and emotional cues, so both `Human Voices Only` and the
existing scene-matched `Soundscape Only` stem remain synchronized. Eighty-eight
scenes use a front-facing environmental-portrait composition. Because the
current evidence does not establish every visibly implied identity attribute,
faces remain in soft shadow, silhouette, reflection, diffusion, or archival
occlusion rather than inventing race, ethnicity, gender, or age. Two sensitive
scenes retain deliberate absence rather than inventing a
historically omitted Indigenous perspective. Rebuild the no-network work
packets with `scripts/prepare_human_figure_visual_path.py`, import them through
`import-visual-prompts`, and check shared timing/audio compatibility with
`scripts/validate_visual_prompt_paths.py`. Generated prompts still require
human editorial approval.

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
`podcast.toe` or a numbered `podcast.<revision>.toe`, runs on the active RTX
3080 workstation and follows the TouchDesigner 2025.32820 timeline. It exposes:

- `prompt_out` for one prompt or two smoothstep-weighted crossfade prompts;
- `caption_out` for the current spoken caption;
- `status_out` for playhead and scene diagnostics;
- `show_control` for live play, audio-source, visual-path, seed, crossfade, and
  color controls plus the optional local-variation profile and child switches;
- `color_out_1` and `color_out_2` for adjusted primary and backup images;
- `voices_only_audio` and `soundscape_audio`, both locked to the same timeline;
- `audiosource_switch`, which sends exactly one selected stem to `audio_out`.
- `syphonspoutout1` and `syphonspoutout2`, the two Spout image senders.

The local 3080 project contains the supplied primary and backup
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
The Local Variations tab defaults to `3080_safe` and Off. The 5090 profile can
independently vary narration text, local speech, visual prompts, interpretive
casting, and variation seeds. A completed bundle becomes active only at a
loop boundary; a missing, late, or invalid bundle leaves the canonical assets
playing.
`Audio Source` offers only `Human Voices Only` and `Soundscape Only`; the
combined review mix is deliberately excluded. `Audio Enabled` gates the
selected stem at the Audio Device Out. Saved paused projects reopen at frame
1 while preserving the saved `Audio Enabled` and source-selection values. See
[touchdesigner/README.md](touchdesigner/README.md) for the adapter boundary.
`Visual Path` independently selects `Original Story Visuals` or `Human
Figures` at the current playhead; switching prompts never switches, restarts,
or combines the selected audio stem.
Brightness `1.0` is neutral in the Level TOP; `0.0` is black and values above
`1.0` brighten the image.

The local `.toe` and `.tox` files are ignored by Git and must not be published.
Use `touchdesigner/update_3080_project.py` for guarded 3080 refreshes. Then run
`touchdesigner/audit_3080_controls.py` and
`touchdesigner/audit_3080_live_events.py`; together they exercise the controls
through deterministic callback checks and the live frame-separated
Parameter Execute path. `touchdesigner/audit_3080_visuals.py` rejects saved
stale backend telemetry and requires a live RTX 3080 backend plus non-black
generator and Spout output. It forces one non-destructive local output cook so
the check also works while the show is paused. Start and stop one
StreamDiffusionTD server at a time for that optional visual check. Keep only
one TouchDesigner project on each OSC port pair; close a competing project or
use temporary unsaved ports for diagnostics.

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

## License

This project is available under the [MIT License](LICENSE).
