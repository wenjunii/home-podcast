# Private 3080 transfer: latest working data and the approved show

The 3080 is the user's authoritative source for the latest project DATA.
Prepare a snapshot here, then stage it on the 4090/5090 later. This is not a
mirror or an automatic merge of another machine's project.

## Prepare on the 3080

Use an explicit checkpoint label. The default is a **read-only plan**, including
consistent catalogue reads and a RAM-only SQL reconstruction test:

```powershell
py -3.10 -m scripts.prepare_working_handoff --bundle .\work\private-handoffs\december-136-3080 --label 3080-2026-11-10-sync
py -3.10 -m scripts.prepare_working_handoff --bundle .\work\private-handoffs\december-136-3080 --label 3080-2026-11-10-sync --apply
```

Replace the example label for the next update. A label freezes one exact source
checkpoint; reusing it after data/code changes is refused. An unchanged repeat
reuses payload objects. Interrupted object copies resume without overwriting
existing objects. Partial or different source checkpoint files are held;
preserve them and choose a new label rather than forcing replacement.
The optional `--source-commit HEX` records a local provenance
hint only; the command does not run Git and always snapshots working files.
Content hashes, not the commit hint, identify the transferred bytes.

The broader command includes:

- The approved 136-story `.40` show: three audio modes, three 619-scene prompt
  paths, 2,862 captions, approved per-story media and native/runtime helpers.
- All current adaptation records (415 at the November 10 preparation), source,
  planning, analysis, review, editorial-exclusion and textual series/podcast
  state. Pending and held records do not become approved by being transported.
- Two consistent catalogue SQL snapshots, checked by reconstruction and row
  counts **in memory**. They are private data, not permission to execute SQL on
  an existing receiver database. Raw live SQLite databases are not copied.

Historical takes, auditions, obsolete playlist audio, other TOE/TOX versions,
models, environments, installed tools, credentials, Git history, active runtime
bundles and worker locks are excluded. Their originals remain on the sender.
This is not a complete historical-media backup. Textual records may refer to
excluded historical media. Source capture timestamps remain capture times.

The narrow `scripts.private_handoff` exporter remains available for approved
136-story playback/editing only. It cannot narrow an existing broader package;
choose a separate folder if you want that smaller scope. Both tools preserve
immutable snapshots and shared objects. Neither prunes old versions, deletes
receiver files, starts models, invokes paid services, or publishes to GitHub.

## What to copy

Wait for a successful preparation command, then copy the **ENTIRE package
folder**, including `objects`, `snapshots`, `handoff.py`, `latest.json`,
`private-handoff-package.json`, `START-HERE.md`, `SENDER-3080.json`,
`VERIFIED-3080.json` and receiver-note ownership/history files. Do not copy only
the small JSON pointers. A trusted checksum-aware private transfer can reuse
unchanged objects. Do not use a mirror/delete option against a working project.

The editable November package is approximately **12 GiB**, not the whole local
audio/work tree. Old objects and snapshots remain, so physical package size can
differ from one snapshot's logical payload size. A package on the same disk is
transfer staging, not a separate-device backup.

The package is **private and unencrypted**. It contains personal archival
material and a licensed component; respect its licence and never publish the
package or media to public GitHub. Credentials and recognizable secret values
fail checks. Exact reviewed legacy HUMAN-permission fields are pinned by path
and value digest; unknown authorization values and nested credential fields
remain blocked. These safeguards are not encryption, comprehensive secret
detection or inspection of every opaque binary. Hashes prove consistency, not
authenticity if an attacker replaces objects and manifests together. Use trusted
private storage and compare the snapshot with the sender's readiness report.

## Later on the 4090 or 5090

1. Preserve the existing project, latest native TOE and local code changes.
   Record its operator/server/model paths and GPU/environment settings.
2. Verify this package and import into a **NEW incoming folder**, never directly
   over an existing project. The standard-library tool needs Python 3.10+ and
   does not execute transferred code, SQL, models or native projects.
3. Compare incoming and existing work. The 3080 supplies the latest DATA, but
   preserve receiver-only changes and machine-specific configuration until
   explicitly reconciled. Do not assume absence means deletion.
4. Plan a controlled merge and a new numbered native project. Keep the old
   version. The `.40` rebinder is 3080-edition-specific: do not run it on an
   existing 4090/5090 project. Do not open/rebind the incoming TOE until its
   local paths and renderer compatibility have been reviewed. Keep live
   variations off until separately enabled. Receiver-native testing is still
   required; no other-PC test is implied by sender verification.

Example PowerShell AFTER copying (edit paths and Python selector as needed):

```powershell
$transfer = 'D:\RecoveredHomes-3080'
$incoming = 'C:\Shows\home-podcast-incoming-3080-2026-11-10'
$sender = Get-Content -LiteralPath (Join-Path $transfer 'SENDER-3080.json') -Raw | ConvertFrom-Json
$latest = Get-Content -LiteralPath (Join-Path $transfer 'latest.json') -Raw | ConvertFrom-Json
if ($sender.snapshot -ne $latest.snapshot) { throw 'Receiver notes do not match the latest snapshot; inspect before continuing.' }
if (Test-Path -LiteralPath $incoming) { throw 'Choose a NEW incoming folder.' }
py -3.10 -I (Join-Path $transfer 'handoff.py') verify --bundle $transfer --snapshot $sender.snapshot
if ($LASTEXITCODE -ne 0) { throw 'Package verification failed.' }
py -3.10 -I (Join-Path $transfer 'handoff.py') import --bundle $transfer --snapshot $sender.snapshot --target $incoming
if ($LASTEXITCODE -ne 0) { throw 'Import dry run failed.' }
py -3.10 -I (Join-Path $transfer 'handoff.py') import --bundle $transfer --snapshot $sender.snapshot --target $incoming --apply
if ($LASTEXITCODE -ne 0) { throw 'Import failed; preserve existing work.' }
py -3.10 -I (Join-Path $transfer 'handoff.py') verify-target --target $incoming
if ($LASTEXITCODE -ne 0) { throw 'Incoming verification failed.' }
```

Import refuses different existing files and never deletes or overwrites them.
It does not initialize Git. Readable root notes are checksummed and their old
versions are archived under `receiver-notes/<snapshot>/` during an update.
The older unmarked November sender envelope is migrated after its manifest,
guide and verification record are checked, retaining all original note bytes.
Once ownership is recorded, unknown manual edits cause a hold. A known interrupted
note update can resume using its pending old/new hashes; preserve and inspect
any unknown or conflicting state instead of forcing it.

The sender's November 8 cache/profile cleanup is **not** a deletion list for
other PCs. Do not recreate or propagate it during transfer. Routine cleanup
still preserves approvals, sources, outputs and required dependencies.

## Request for the receiving project chat

The latest DATA comes from this 3080 package. Read START-HERE.md and
SENDER-3080.json, verify, and stage in a fresh incoming folder. Inspect my
existing project read-only first. Compare code/data and report conflicts;
preserve native versions, GPU/environment/operator settings, models,
credentials and receiver-only work. Do not mirror deletions, execute catalogue
SQL against existing databases, enable live generation, start servers, make
paid calls, write to GitHub or overwrite a TOE. Plan the controlled merge and
new native version after showing the comparison.
