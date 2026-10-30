# Continue Recovered Homes on another PC

## Current local-first handoff: 136 stories / podcast.40.toe

GitHub is optional. The private handoff tool snapshots the **current working
files**, including uncommitted code, ignored approved media and the runtime
dependencies under `work/`. It never invokes Git, a provider, a model or a
network client. Existing local Git history and GitHub remotes are left alone.

The default editable package includes the selected 3080 `.40`, all three
playlist audio modes, three 619-scene prompt paths, 2,862 captions, imported
controller dependencies, source/adaptation/personal-review history for the
136 selected stories, their approved per-story audio and existing human
approval receipts. It does **not** infer new approvals or resume any deferred
production. Historical receipts can mention a larger reviewed cohort; that
does not put excluded/deferred media into this package.

### Export on the current PC

From the project directory, use any dedicated private package folder. For
example, the local package prepared during implementation is under
`work/private-handoffs/december-136-3080/`:

```powershell
py -3.10 -m scripts.private_handoff plan
py -3.10 -m scripts.private_handoff export --bundle .\work\private-handoffs\december-136-3080
py -3.10 -m scripts.private_handoff export --bundle .\work\private-handoffs\december-136-3080 --apply
py -3.10 -m scripts.private_handoff verify --bundle .\work\private-handoffs\december-136-3080
```

`plan`, and `export`/`import` without `--apply`, are read-only. A package stores
immutable SHA-256 objects and snapshot manifests, not a new full media copy
for every revision. Repeating an unchanged export copies **zero payload
bytes**. New snapshots add only changed objects; older snapshots remain.
Copy the **entire package folder**, including `objects`, `snapshots`,
`latest.json` and `handoff.py`, through your private drive/network workflow.
Use a checksum-aware incremental transfer if available. Do not copy only
`latest.json`. A copy on the same disk is a transfer staging area, not a backup.

The editable package is roughly 11.7 GB initially; `--playback-only` omits
individual story media and editorial history for a smaller playback package.
Do not use the playback-only package as the sole editorial backup.

### Import on another PC without GitHub or a cloned repository

Python 3.10+ is sufficient for the transfer tool; it has no third-party
dependencies. Run the package's standalone tool, using a **fresh project
directory**, not the existing 5090 project:

```powershell
py -3.10 D:\RecoveredHomes-private\handoff.py verify --bundle D:\RecoveredHomes-private
py -3.10 D:\RecoveredHomes-private\handoff.py import --bundle D:\RecoveredHomes-private --target C:\Shows\home-podcast
py -3.10 D:\RecoveredHomes-private\handoff.py import --bundle D:\RecoveredHomes-private --target C:\Shows\home-podcast --apply
py -3.10 D:\RecoveredHomes-private\handoff.py verify-target --target C:\Shows\home-podcast
```

Import verifies the complete selected snapshot **before** copying. Identical
files are skipped. Different existing files, file/directory conflicts,
symlinks/junctions, traversal paths and other `.toe` editions are refused;
nothing is overwritten or deleted. An interrupted import can resume when its
completed files are unchanged. A different snapshot with conflicting files
belongs in a fresh project directory. No Git history is transferred or
initialized; you may keep using local Git separately, without GitHub.

### Rebind the moved .40 in TouchDesigner

Install/license TouchDesigner 2025.32820 and the required renderer/model
environment separately. The handoff intentionally excludes model weights,
virtual environments and machine-specific paid-operator server paths.
With both StreamDiffusionTD servers/streams stopped, open the imported
`podcast.40.toe`. Saved old absolute paths may show errors until rebinding.
In its Python Textport:

```python
exec(open(r"C:\Shows\home-podcast\touchdesigner\rebind_private_handoff.py", encoding="utf-8").read())
rebind_private_handoff()
```

This verifies the imported files, updates our connector's file parameters
**and embedded callback helper paths**, reloads the current controller and
leaves playback paused. It refuses any 5090 project/profile, never starts
servers, never changes paid-operator environment paths and never saves a TOE.
If a native rebind fails, leave playback stopped and reopen the imported file
before investigating. Save a new numbered edition yourself after testing;
keep the imported `.40` unchanged as the verified reference. Do **not** run the
older pilot-only `rebind_project_paths.py` for this edition.

### Privacy and preservation

- The package is **private and unencrypted**: it includes archived personal
  material and a licensed component inside the selected TOE. Never publish it
  or upload it to the public GitHub repository. Respect the operator's license.
- Credentials, `.env`, authentication files, Git history, model caches and old
  TOEs are excluded. Recognizable key/private-key patterns and nonempty JSON
  credential fields fail the export. This is a safeguard, not a comprehensive
  secret detector, encryption or inspection of every opaque embedded binary.
- Hashes detect incomplete/changed transfers, not authenticity against an
  attacker who can replace both manifests and objects. Use trusted private
  storage and compare the snapshot ID with the sender before executing code.
- Source media, narration text, prompt/caption clocks, existing approval state,
  `.40`, all older projects and the 5090 setup are not rewritten. Historical
  review pages, generation caches and older TOE editions are not a complete
  part of this scoped package; preserve their originals separately if needed.

## Preserved GitHub/pilot restore workflow

### Optional current code-only GitHub sync

The public sync is for source, tests, schemas, generic configuration and
documentation only. Narration records/drafts, recovered full-source exports,
private handoff objects, audio, TOEs, environment files and machine credentials
stay local. Ignore rules are not sufficient by themselves: before a commit,
run the staged-blob gate, and before pushing check every new commit's blobs:

```powershell
py -3.10 -m scripts.check_public_sync
py -3.10 -m scripts.check_public_sync --base origin/main
```

The gate is read-only, uses no network and never prints credential contents.
It scans the **actual staged/committed blobs**, so cleaning only the working
copy cannot hide a staged secret, and deleting a secret in a later commit does
not clear an unsafe earlier commit. It also blocks non-code paths, binary
payloads, symlinks and oversized source files. A successful gate is an added
safeguard, not a comprehensive secret detector or permission to publish private
data. Commit/push/PR actions still require an explicit user request.

Public tests use synthetic stories to exercise source preservation and the
editorial-review gate, including rejection after an approved fixture changes.
Two historical production-snapshot integration tests run only when their
private files are present; those records do not need to be published to run
the code tests. Synthetic test reviews never count as production approval.

The following describes the older public-source/pilot handoff, not a complete
restore of the current private `.40` storytelling show.

The public repository contains the durable, non-secret project state needed to
continue editorial and visual-sequencer work:

- the canonical `data/exports/stories_*.md` inputs;
- the portable current story-card snapshot;
- locked episode manifests, scripts, transcripts, captions, and visual scenes;
- the final voices-only and soundscape-only pilot MP3s and timing timeline;
- the 91 hashed raw SFX responses needed for zero-cost cache restoration;
- Python production code, tests, TouchDesigner installers, and controller code.

Rebuildable SQLite state, intermediate WAV files, obsolete sound experiments,
credentials, and TouchDesigner `.toe`/`.tox` files are deliberately excluded.

The December self-narration text state, local-audio configuration, empty or
reviewed synthetic voice roster metadata, and local-audio handoff are portable.
Model weights and the generated `audio/storytelling-real-december/` tree are
not. After a VoiceDesign reference or production audio exists, transfer that
audio tree through private large-file storage and keep the same repository-
relative paths; Git alone cannot restore an approved reference voice or a
rendered section cache. See `docs/LOCAL_AUDIO_3080.md` before moving an active
audio production run.

The preserved 45-story 3080 local show is `podcast.28.toe` (45 stories, 55:35.680),
with 166 revised scenes per visual path and unchanged audio/captions.
For a private cross-PC handoff also preserve
`work/storytelling-real-december/playlist-45-detail-2026-10-29/`,
the approved per-story `visuals/detail-approved-2026-10-29/` plans, the
`work/storytelling-real-december/local-audio/approvals/prompt-detail-review-45-v2-2026-10-29.json`
receipt, and
`work/storytelling-real-december/playlist-45-2026-10-29/`, the reused
`work/storytelling-real-december/playlist-35-2026-10-29/segments/`, and
`audio/storytelling-real-december/playlist-45-2026-10-29/`, plus the source
story audio/visual/caption trees referenced by the manifest. Keep the old
`.27` and `.26` plus their original folders if those reproducible setups are needed. These
large local assets and paid operators are not part of a Git-only restore.
Do not copy credentials or overwrite the separate 5090 project. This note
does not indicate that any new sync or upload has occurred.

## Restore the deterministic project state

Clone the repository, install Python 3.10 or newer, and run:

```powershell
python -m home_podcast doctor
python -m home_podcast ingest
python -m home_podcast import-cards .\data\story_cards\current-cards.jsonl
python -m home_podcast status
```

`ingest` rebuilds `data/catalog.sqlite3` from the tracked Markdown exports.
`import-cards` restores the embedded analyzer provenance and validates every
card against the current story ID, content hash, controlled theme vocabulary,
and verbatim quotations. Neither command makes a network or paid-provider
request.

The current portable snapshot contains 91 analyzed December 2013 story cards.
The canonical Markdown snapshot contains 1,652 unique stories across five
capture months and ten languages. A clean restore reports 1,652 present and
eligible stories, 91 current cards, and zero exact duplicates.
After analyzing new stories, refresh it with:

```powershell
python -m home_podcast export-cards `
  --output .\data\story_cards\current-cards.jsonl
```

Commit the refreshed snapshot together with any updated `stories_*.md` files.
Do not commit `data/catalog.sqlite3`; it is only a rebuildable local index.

## Update the source export snapshot

If the extractor is cloned beside this repository, use the guarded synchronizer
instead of copying a wildcard directly:

```powershell
python .\scripts\sync_story_exports.py
python .\scripts\sync_story_exports.py --apply
python -m home_podcast ingest
python -m home_podcast status
python -m home_podcast export-cards `
  --output .\data\story_cards\current-cards.jsonl
```

The first command is a no-write report. The second copies only parsed
`stories_*.md` files and verifies the destination byte-for-byte. It never
copies `matches*` files or the compressed JSONL export. A stale destination
story file stops the operation unless `--prune` was explicitly supplied after
reviewing the dry run. Common Crawl timestamps are capture times, not
publication dates.

## Restore the pilot and TouchDesigner setup

The repository includes:

```text
episodes/2013-12.01/audio/2013-12.01-voices-only.mp3
episodes/2013-12.01/audio/2013-12.01-soundscape-only.mp3
episodes/2013-12.01/audio/2013-12.01-timeline.json
episodes/2013-12.01/audio/sfx-responses/
episodes/2013-12.01/transcripts/
episodes/2013-12.01/visuals/2013-12.01-visual-scenes.json
episodes/2013-12.01/visuals/2013-12.01-visual-scenes-human-figures.json
touchdesigner/
```

Both Show Control stems are ready immediately after cloning. To restore the
editable scene-level SFX cache without an ElevenLabs credential or paid call:

```powershell
python .\scripts\sync_pilot_sfx_cache.py validate
python .\scripts\sync_pilot_sfx_cache.py restore
python -m home_podcast generate-sfx `
  --jobs .\work\sfx\2013-12.01-scene-jobs.jsonl
```

The final dry run must report 91 cached jobs and zero pending calls. The
portable response manifest is bound to the current cue prompts, model,
durations, and SHA-256 file hashes; a mismatch fails closed.

The active local TouchDesigner working file is the RTX 3080 `podcast.toe` or a
numbered `podcast.<revision>.toe`, targeting TouchDesigner 2025.32820. It is
intentionally not on GitHub because it contains the paid StreamDiffusionTD
component.

Transfer the 3080 file separately through private storage, or create a fresh
`.toe`, install StreamDiffusionTD under your license, and follow
`touchdesigner/README.md` to install the tracked connector. After transferring
the 3080 file into the cloned repository root, run
`touchdesigner/update_3080_project.py` from the TouchDesigner Textport. The
guarded updater refuses unrelated filenames, refreshes both audio-stem paths
and both visual-prompt paths, restores the two Spout senders, and leaves the
paid components untouched. Inspect the result and save a new numbered 3080
revision.

Before saving, run `touchdesigner/audit_3080_controls.py` and
`touchdesigner/audit_3080_live_events.py` from the Textport. They reject
unrelated filenames, exercise all 19 Show Control parameters, including the
independent original-versus-human-figure visual-path menu, verify the callback
and output network, and restore the original show state without saving.

For a generated-image check, start only one StreamDiffusionTD server, wait for
model initialization, and run `touchdesigner/audit_3080_visuals.py`. The
visual audit requires an active RTX 3080 local backend, a current output-memory
name, and non-black color and Spout-source pixels. It forces one non-destructive
local TOP cook so a paused project can prove the complete output path.
Backend tables persist in the `.toe` and may display legacy connection labels
or errors from the machine that last saved it; the output-name timestamp is
the server-session start time, not a heartbeat. Stop that server and confirm
its process has exited before starting the other component. Never run both
servers at once.

Do not keep two TouchDesigner projects listening on the same OSC receive port.
The primary component ships with 8574/8583. Close the other project or use a
temporary unique port pair for the active 3080 component and generated server
config, then restore the shipped values without saving the diagnostic
override.

## Credentials

Credentials are not part of the repository. On the new PC, set provider keys
only as temporary environment variables when explicitly running a paid media
step:

```powershell
$env:CAPRIOLE_API_KEY = "<set locally only when requested>"
$env:ELEVENLABS_API_KEY = "<set locally only when requested>"
```

Clear them after use:

```powershell
Remove-Item Env:CAPRIOLE_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:ELEVENLABS_API_KEY -ErrorAction SilentlyContinue
```

Do not place keys in `podcast.json`, shell scripts, logs, caches, transcripts,
jobs, documentation, or `.toe` files.
