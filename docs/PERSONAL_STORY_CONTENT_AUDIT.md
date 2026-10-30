# Personal-story content audit — October 28, 2026

The audition problems originated in the scripts and selection pipeline, not in
Qwen inventing words. Warm Atlantic's input literally contained "The source
says" and came from song lyrics. Intimate Indian English's input was the
PicaJet blog's sidebar, including archive months and travel links.

## Scope and current status

All 415 current adaptation files and their frozen source jobs were screened.
All 65 previously authored/translated spoken drafts were inspected. Full
source-backed approvals were initially completed for nine selected personal stories;
six adaptations were revised and reimported, with zero rejections. A subsequent
long-form test adds Elaine Leeder's essay as the tenth reviewed personal story,
replacing one conservative copy with a complete conversational adaptation. The audit
does not claim all 415 sources have received full semantic editorial review.

- 10 stories currently pass the personal-story production gate (25 sections,
  3,067 words; approximately 19–23 minutes before actual rendering).
- 405 drafts are blocked, including 348 remaining conservative source copies.
  These are not all necessarily unsuitable; they need source review and either
  genuine spoken adaptation or a documented hold.
- 367 cards have mechanical summary scaffolds; 380 contain unreviewed passage
  inventories. These overlapping counts are not semantic story analyses.
  Reviewed sidecar analyses supersede them for the approved personal path.
- Remaining screening flags include 20 source-commentary drafts, 21 archive
  month lists, 88 navigation-text drafts, and one explicit promotional pattern.
  Counts overlap. Absence of these patterns never proves personal relevance.
- No self-narrated visual-prompt files exist yet. The existing podcast visuals
  are a separate preserved collection and were not rewritten.

The approximately 60-hour estimate measured all draft text, including webpage
furniture and generic material. It is not a reliable production runtime.

## Editorial repairs

PicaJet is now **What I Want My Grandchildren to See**: a short first-person
memory of an old building and a wish to share disappearing heritage. Only the
preview is available; no later trip or resolution is invented. Western Canada
is supported by the article title, while the unrelated sidebar destinations
are excluded. Archive dates are not personal events.

Other changes remove a blog-comment invitation, a generic outdoor-activity
list, unsupported embellishment, and stilted phrasing. Actual story details
such as the year of a childhood candy purchase or fourteen hours of sleep are
retained. The Warm Atlantic lyrical source is held: a lyrical "I" is not enough
to establish a historical witness.

Original drafts are recoverable under
`work/storytelling-real-december/quality/reviewed-batch-2026-10-28/original-adaptations`.
No frozen source job, manifest, existing audio, podcast artifact, or `.toe`
project was overwritten. The initial repair batch changed six draft adaptations;
the long-form test adds a seventh revision. Its previous draft is recoverable at
`work/storytelling-real-december/local-audio/long-story-proof-2026-10-28/original-artifacts`.

## Gates and next production step

`personal-story-review.json` binds editorial approval to source and adaptation
hashes, exact personal-experience evidence, approved sections, and reviewed
locations. Missing, held, incomplete, or stale reviews block auditions, local
speech preparation/render/assembly, and local variations. Initial personal
visual import and live visual variation require section IDs and an exact
personal-story excerpt. First-person storytelling does not require a first-person
camera: front-facing environmental portraits remain supported.

Run the repeatable no-network screening pass:

```powershell
py -3.10 -m scripts.audit_personal_story_content --config storytelling.real-december.json
```

Detailed results and the incremental queue are in
`work/storytelling-real-december/quality/personal-story-audit.json` and
`work/storytelling-real-december/quality/personal-story-review-queue.jsonl`.
The production index is `series/2013-12/storytelling-production-index.json`.
The full preflight deliberately reports `valid: false` while any draft is
blocked; its section inventory contains only approved stories.

All eight original audition plans are blocked by current content review or
missing revision fingerprints. Their WAVs are preserved. A replacement plan
using reviewed stories is stored at
`work/storytelling-real-december/local-audio/reviewed-voice-audition-plan.json`:
all eight replacement auditions were rendered and approved by the user. Three
complete short adaptations were then rendered in five sections; their listening
page is `audio/storytelling-real-december/three-story-proof-2026-10-28/index.html`.
Voice approval is separate from approval of those complete renders.

The requested long-form test, **An Outsider on the Inside**, preserves Elaine
Leeder's first-person account in ten sections, with one previously approved
Warm Atlantic performer. The accent is an artistic choice, not a claim about
Leeder's voice. Source evidence, biography separation, casting, and the exact
ten-call offline dry run are recorded under
`work/storytelling-real-december/local-audio/long-story-proof-2026-10-28`.
`run-state.json` records rendering status; the listening page and technical
report are created only after every section passes assembly checks. This test
does not approve bulk production or generate soundscapes or visuals.
The completed test is **9 minutes 46 seconds**, with 1,879 spoken-script words,
ten generated sections, no pending calls, and no clipped samples. Its listening
page is `audio/storytelling-real-december/long-story-proof-2026-10-28/index.html`.
The section near 8:08 measures quieter and faster and is marked for listening
review. Script-derived SRT/VTT cues use section boundaries; they are not an
independent transcription or word-level alignment. Generation was entirely
local with cached weights, zero network or paid calls, and no `.toe` or 5090 changes.

Continue the 405-entry editorial queue in source-reviewed batches before bulk
audio generation. Do not approve the queue mechanically or pad fragments with
general information. Archive provenance, source limitations, and performer
disclosures belong in metadata, never spoken exposition.
