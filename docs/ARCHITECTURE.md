# Architecture and state rules

## Story identity

A stable story ID is derived from:

- language
- source URL
- Common Crawl WARC source path
- the smallest extractor match reference

The smallest match reference distinguishes the rare captured pages containing
multiple independent extracted stories. Additional match references can be
appended without changing that discriminator. The content hash is stored
separately and changes whenever the extracted story text changes.

Every scan records:

- first and last seen timestamps
- current content and record hashes
- all historical record versions
- current presence or absence
- exact-content duplicates
- crawl timestamp and month
- language and provenance
- quality flags without altering the raw source

## Incremental invalidation

```text
source metadata changes
  → new record version, source ID unchanged

story text changes
  → new content hash
  → previous story card becomes stale
  → story is exported for analysis again

script line changes
  → new speech cache key
  → only that audio clip is regenerated

sound prompt, generator, or duration changes
  → new sound-effect cache key
  → no speech clip is regenerated

cue placement, gain, fades, or ducking changes
  → only the soundscape stem and combined review mix are rebuilt
```

No high-water mark is used. A later extraction can add a previously unseen
story from an older crawl month, so every scan compares stable IDs and hashes.

## Archive volume lifecycle

- **Open:** new stories may change clusters and themes.
- **Locked:** the episode evidence set is fixed for production.
- **Published:** manifest, script, source hashes, audio, and transcript are
  immutable.

A late discovery from a published month becomes a supplement (`2013-12.S1`) or
a later cross-month thematic installment. It never silently rewrites a released
episode.

## AI trust boundaries

The story analyzer may classify and summarize but cannot change provenance.
The script model sees only the selected evidence packet. The validator ensures
that all cited story IDs are in that packet and every selected story is used.
Segments marked as exact quotes receive a normalized substring check against
the source.

AI checks are useful for tone and unsupported-claim detection, but deterministic
validation remains the final gate wherever a machine-checkable rule exists.

## Sound-design trust boundary

Non-voice audio is not evidence. Every cue must be marked either as
illustrative sound design or as a licensed recording with a source and credit.
The production transcript discloses the sound-design layer and can caption
each audible cue. Generated sound must never be described as an archival
recording or as audio captured from a story's people, place, or event.

The renderer emits synchronized voices-only and non-human-only tracks, plus a
combined review mix. A nearly subliminal base ambience spans the full speech
timeline. Thematic section beds are generated as 30-second seamless sources and
extended locally until the next eligible section. If a proposed section is
shorter than the configured minimum, its cue is suppressed and the preceding
bed continues. This coverage decision is written into the timeline.

## Rotating episode cast

The show bible defines three conversational functions, while
`config/voice_roster.json` contains several role-matched people and voices.
Each episode evaluates every valid role-compatible lineup, keeps the lineups
with maximum accent diversity, applies a deterministic pseudo-random
episode-level tie-break, and freezes the result in
`episodes/<episode>/cast.json`. Rebuilding an episode reuses that file; adding
voices later cannot silently change an existing cast.

The on-air conversation treats the cast as ordinary podcast hosts and never
discusses how their voices are produced. Internal cast metadata retains the
provider, voice IDs, and verified accent labels for reproducibility. Fragment
readings never claim to be interviews, impersonations, or recordings of the
original writers.

New community voices follow a two-stage gate. Metadata screening checks
verified English, availability notice, and credit multiplier; a same-script
audition then checks naturalness, emotion, pronunciation, fatigue, and
artifacts. Only candidates that pass listening review move from
`config/accent_voice_candidates.json` into `config/voice_roster.json`.
Accents are cast from natural voice characteristics and never requested through
caricature or imitation tags.
