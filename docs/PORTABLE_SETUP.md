# Continue Recovered Homes on another PC

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
After analyzing new stories, refresh it with:

```powershell
python -m home_podcast export-cards `
  --output .\data\story_cards\current-cards.jsonl
```

Commit the refreshed snapshot together with any updated `stories_*.md` files.
Do not commit `data/catalog.sqlite3`; it is only a rebuildable local index.

## Update the source export snapshot

If the extractor is cloned beside this repository, copy only its story exports:

```powershell
Copy-Item `
  ..\cc-home-extractor\data\exports\stories_*.md `
  .\data\exports\ `
  -Force

python -m home_podcast ingest
python -m home_podcast status
```

Never copy `matches*` files or the compressed JSONL export into this project.
Common Crawl timestamps are capture times, not publication dates.

## Restore the pilot and TouchDesigner setup

The repository includes:

```text
episodes/2013-12.01/audio/2013-12.01-voices-only.mp3
episodes/2013-12.01/audio/2013-12.01-soundscape-only.mp3
episodes/2013-12.01/audio/2013-12.01-timeline.json
episodes/2013-12.01/audio/sfx-responses/
episodes/2013-12.01/transcripts/
episodes/2013-12.01/visuals/2013-12.01-visual-scenes.json
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

The active local TouchDesigner working file is `podcast.5090.toe` (currently
saved as `podcast.5090.24.toe`), targeting TouchDesigner 2025.32820. It is
intentionally not on GitHub because it contains the paid StreamDiffusionTD
component. The `podcast.3080*.toe` files are reference inputs only during 5090
work and must not be updated or saved.

Transfer the 5090 file separately through private storage, or create a fresh
`.toe`, install StreamDiffusionTD under your license, and follow
`touchdesigner/README.md` to install the tracked connector. After transferring
the 5090 file into the cloned repository root, run
`touchdesigner/update_5090_project.py` from the TouchDesigner Textport. The
guarded updater refuses non-5090 filenames, refreshes both audio-stem paths and
Show Control, restores the two 5090 Spout senders, and leaves the paid
components untouched. Inspect the result and save a new numbered 5090
revision.

Before saving, run `touchdesigner/audit_5090_controls.py` and
`touchdesigner/audit_5090_live_events.py` from the Textport. They refuse 3080
filenames, exercise all 18 Show Control parameters, verify the callback and
output network, and restore the original show state without saving.

For a generated-image check, start only one StreamDiffusionTD server, wait for
model initialization, and run `touchdesigner/audit_5090_visuals.py`. The
visual audit requires an active RTX 5090 local backend, a current output-memory
name, and non-black color and Spout-source pixels. It forces one non-destructive
local TOP cook so a paused project can prove the complete output path.
Backend tables persist in the `.toe` and may display legacy connection labels
or errors from the machine that last saved it; the output-name timestamp is
the server-session start time, not a heartbeat. Stop that server and confirm
its process has exited before starting the other component. Never run both
servers at once.

Do not keep two TouchDesigner projects listening on the same OSC receive port.
The primary component ships with 8574/8583. Close the other project or use a
temporary unique port pair for the active 5090 component and generated server
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
