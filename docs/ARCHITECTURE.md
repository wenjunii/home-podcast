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

## Synthetic-host disclosure

Every episode must explain that its hosts and fragment readers are synthetic.
Fragment readers perform archived text; they never impersonate or simulate the
original writers.
