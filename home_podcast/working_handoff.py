"""Repeatable private 3080 working-state handoff; standard library, no Git/network.

Default is a read-only plan. --apply freezes consistent catalogue SQL as DATA,
adds current working text to the approved show, and publishes receiver notes.
Never merges into another PC, executes transferred code, or loads media models.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sqlite3
import sys

from . import private_handoff as h

STATE = "work/private-handoff-state"
GUIDE = "docs/PC_HANDOFF.md"
ROOT_NOTES = ("START-HERE.md", "SENDER-3080.json", "VERIFIED-3080.json")
NOTE_FORMAT = "recovered-homes-receiver-notes-v1"
EXCLUDED_COMPONENTS = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".venv", "node_modules", "site-packages", "segments", "cache", "locks", "pids"}
EXCLUDED_PREFIXES = (
    "work/private-handoffs/", "work/private-handoff-state/",
    "work/cross-pc-prep-",
    "work/storytelling-real-december/ambient-runtime/models/",
    "work/storytelling-real-december/ambient-runtime/vendor/",
    "work/storytelling-real-december/ambient-runtime/venv/",
    "work/storytelling-real-december/local-audio/asr-runtime/",
    "work/storytelling-real-december/local-audio/chatterbox-runtime/",
    "work/storytelling-real-december/tools/", "work/storytelling-real-december/runtime/",
)


def excluded(name):
    low = name.casefold()
    parts = low.rstrip("/").split("/")
    leaf = parts[-1]
    return (low.startswith(EXCLUDED_PREFIXES)
        or any(part in EXCLUDED_COMPONENTS or part.startswith((".venv-", ".env")) for part in parts)
        or leaf in {"auth.json", "credentials.json", "lock.json", "locks.json", "worker-lock.json", "handoff.lock"}
        or leaf.startswith("matches") or leaf.endswith((".lock", ".lock.json", "-lock.json")))


def working_files(root):
    for folder in ("narrations", "data", "series", "cohorts", "episodes", "work"):
        base = h.checked_path(root, folder)
        if not base.exists():
            continue
        for current, directories, filenames in os.walk(base, followlinks=False):
            kept = []
            for leaf in sorted(directories):
                name = (Path(current) / leaf).relative_to(root).as_posix()
                if not excluded(name + "/"):
                    h.checked_path(root, name)  # Refuse relevant junctions, never follow them.
                    kept.append(leaf)
            directories[:] = kept
            for leaf in sorted(filenames):
                path = Path(current) / leaf
                name = path.relative_to(root).as_posix()
                if not excluded(name) and path.suffix.casefold() in h.TEXT:
                    yield name


def catalogue_snapshot(path):
    """A consistent read transaction; scratch reconstruction is RAM-only."""
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        h.require(connection.execute("PRAGMA quick_check").fetchone()[0] == "ok", "Catalogue quick_check failed")
        tables = [r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        quoted = lambda name: '"' + name.replace('"', '""') + '"'
        counts = {name: connection.execute("SELECT COUNT(*) FROM " + quoted(name)).fetchone()[0] for name in tables}
        data = ("\n".join(connection.iterdump()) + "\n").encode("utf-8")
    finally:
        connection.close()
    h.require(not h.SECRET.search(data), "Credential-shaped catalogue content (contents suppressed)")
    scratch = sqlite3.connect(":memory:")
    try:
        scratch.execute("PRAGMA temp_store=MEMORY")
        scratch.executescript(data.decode("utf-8"))
        h.require(scratch.execute("PRAGMA quick_check").fetchone()[0] == "ok", "Catalogue RAM restore failed")
        for name, count in counts.items():
            h.require(scratch.execute("SELECT COUNT(*) FROM " + quoted(name)).fetchone()[0] == count, "Catalogue RAM restore row count mismatch")
    finally:
        scratch.close()
    return data, counts


def build_plan(root, label, source_commit=None):
    root = Path(root).resolve()
    h.require(bool(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", label)) and not h.SECRET.search(label.encode()), "Use a simple non-secret checkpoint label")
    h.require(source_commit is None or bool(re.fullmatch(r"[0-9a-f]{40,64}", source_commit)), "Invalid optional source commit")
    selected, expected, metadata = h.build_selection(root, editable=True)
    base_names = set(selected)
    for name in working_files(root):
        selected.setdefault(name, set()).add("latest_working_text_state")
    if (root / "podcast.real-december.json").is_file():
        selected.setdefault("podcast.real-december.json", set()).add("preserved_podcast_configuration")
    selected.setdefault(GUIDE, set()).add("receiver_instructions")
    generated = {}
    catalogues = []
    for filename in ("catalog.sqlite3", "catalog-real-december.sqlite3"):
        source = h.checked_path(root, "data/" + filename)
        h.require(source.is_file(), "Missing source catalogue: " + filename)
        data, counts = catalogue_snapshot(source)
        name = STATE + "/" + label + "/catalog-snapshots/" + filename + ".sql.txt"
        generated[name] = data
        catalogues.append(dict(source="data/" + filename, export=name, sha256=h.digest_bytes(data), table_rows=counts,
            quick_check="ok", ram_restore="passed", source_connection="read_only", execution_on_receiver="never automatic"))
    directory = root / "narrations/real-december"
    records = sum((path / "adaptation.json").is_file() for path in directory.iterdir() if path.is_dir()) if directory.is_dir() else 0
    context = dict(format="recovered-homes-working-state-v1", label=label, authoritative_data_pc="3080",
        source_commit_hint=source_commit, code_provenance="Exact current working bytes; commit hint does not certify a clean worktree",
        adaptation_records=records, approved_playback_stories=metadata["stories"], catalogue_snapshots=catalogues,
        approval_policy="Preserve all existing pending/held/approved statuses; transport grants no new approval",
        receiver_policy="Stage in a fresh folder and compare; no merge, deletion, SQL execution or native project update",
        omitted="Historical audio, other native project versions, model/environment/tool installations, credentials, Git history, active runtime and locks")
    generated[STATE + "/" + label + "/sender-inventory.json"] = h.canonical(context)
    metadata.update(selection_mode="latest-working-state-plus-approved-show", authoritative_data_pc="3080", editorial_records=records,
        working_state_label=label, source_commit_hint=source_commit, additional_working_text_files=len(set(selected)-base_names),
        catalogue_restore="SQL is private data, not permission to execute on an existing database", receiver_merge="Requires later user-directed comparison")
    body = h.inventory(root, selected, expected, metadata)
    for name, data in generated.items():
        h.safe_name(name)
        body["files"].append(dict(path=name, sha256=h.digest_bytes(data), size=len(data), roles=["frozen_sender_state"]))
    body["files"].sort(key=lambda item: item["path"])
    h.validate_manifest(body)
    snapshot = h.digest_bytes(h.canonical(body))
    frozen_name = STATE + "/" + label + "/manifest.json"
    frozen = h.checked_path(root, frozen_name)
    h.require(not frozen.exists() or frozen.read_bytes() == h.canonical(body), "Checkpoint label already freezes different content; use a new label")
    for name, data in generated.items():
        path = h.checked_path(root, name)
        h.require(not path.exists() or path.read_bytes() == data, "Preserve existing checkpoint file; use a new label")
    return dict(root=root, label=label, body=body, snapshot=snapshot, generated=generated, frozen_name=frozen_name, context=context)


def read_note_state(bundle, new_snapshot):
    """Refuse unknown edits; support exact old/new note bytes after interruption."""
    bundle = Path(bundle).absolute()
    pending_path = h.checked_path(bundle, "receiver-notes.pending.json")
    marker_path = h.checked_path(bundle, "receiver-notes.json")
    existing = {}
    for name in ROOT_NOTES:
        path = h.checked_path(bundle, name)
        if path.exists():
            h.scan(path, name)
            existing[name] = path.read_bytes()
    if pending_path.exists():
        pending = h.read(pending_path)
        h.require(set(pending) == {"format", "snapshot", "previous_snapshot", "old", "new"}
            and pending.get("format") == NOTE_FORMAT and pending.get("snapshot") == new_snapshot
            and isinstance(pending.get("previous_snapshot"), str) and bool(h.HEX.fullmatch(pending["previous_snapshot"])),
            "Different or unknown receiver-note update pending; inspect it")
        for name in ROOT_NOTES:
            actual = h.digest_bytes(existing[name]) if name in existing else None
            h.require(actual in (pending["old"].get(name), pending["new"][name]), "Receiver notes were edited during update; preserve them")
        return dict(existing=existing, snapshot=pending["previous_snapshot"], pending=pending)
    if marker_path.exists():
        marker = h.read(marker_path)
        h.require(set(marker) == {"format", "snapshot", "files"} and marker.get("format") == NOTE_FORMAT
            and set(marker.get("files", {})) == set(ROOT_NOTES), "Invalid receiver-note ownership marker")
        h.require(all(name in existing and h.digest_bytes(existing[name]) == checksum for name, checksum in marker["files"].items()), "Receiver notes were locally edited; preserve them")
        previous = marker["snapshot"]
        h.load_bundle(bundle, previous)
    elif existing:
        # Migration of the verified November 3080 envelope, never arbitrary files.
        h.require(set(existing) == set(ROOT_NOTES), "Unknown partial receiver notes; preserve them")
        sender = json.loads(existing["SENDER-3080.json"])
        previous = sender.get("snapshot")
        old_body, _ = h.load_bundle(bundle, previous)
        h.require(h.digest_bytes(existing["START-HERE.md"]) == sender.get("start_here_sha256")
            and any(e["sha256"] == sender.get("start_here_sha256") for e in old_body["files"]), "Unknown readable guide; preserve it")
        proof = json.loads(existing["VERIFIED-3080.json"])
        h.require(proof.get("status") == "ready_for_private_transfer" and proof.get("snapshot") == previous
            and proof.get("files_verified") == len(old_body["files"]), "Unknown legacy verification note; preserve it")
    else:
        previous = new_snapshot
    h.require(bool(h.HEX.fullmatch(previous)), "Invalid previous note snapshot")
    for name, data in existing.items():
        h.require(not h.SECRET.search(data), "Credential-shaped receiver note (contents suppressed)")
        archive = h.checked_path(bundle, "receiver-notes/" + previous + "/" + name)
        h.require(not archive.exists() or archive.read_bytes() == data, "Preserve different archived receiver notes")
    return dict(existing=existing, snapshot=previous, pending=None)


def store_plan(bundle, body):
    """Object cost inspection without materializing virtual catalogue files."""
    bundle = Path(bundle).absolute()
    h.require(not h.checked_path(bundle, "handoff.lock").exists(), "Package is locked")
    if bundle.exists() and any(bundle.iterdir()):
        marker = h.read(h.checked_path(bundle, "private-handoff-package.json"))
        h.require(marker.get("format") == h.FORMAT, "Use an empty folder or a private handoff package")
        launcher = h.checked_path(bundle, "handoff.py")
        if launcher.exists():
            h.require(h.sha(launcher) in marker.get("allowed_bootstrap_sha256", []), "Standalone tool was locally edited; preserve it")
    unique = {entry["sha256"]: entry for entry in body["files"]}
    pending = []
    for entry in unique.values():
        path = h.checked_path(bundle, h.object_name(entry["sha256"]))
        if path.exists():
            h.require(path.is_file() and path.stat().st_size == entry["size"] and h.sha(path) == entry["sha256"], "Existing object is corrupt; preserve it")
            h.scan(path, entry["path"])
        else:
            pending.append(entry)
    return dict(files=len(body["files"]), unique_objects=len(unique), new_objects=len(pending), reused_objects=len(unique)-len(pending), copy_bytes=sum(e["size"] for e in pending))


def publish_notes(bundle, plan):
    body, snapshot = plan["body"], plan["snapshot"]
    guide = next(entry for entry in body["files"] if entry["path"] == GUIDE)
    bootstrap = next(entry for entry in body["files"] if entry["path"] == "home_podcast/private_handoff.py")
    sender = dict(snapshot=snapshot, label=plan["label"], authoritative_data_pc="3080", files=len(body["files"]),
        payload_bytes=sum(e["size"] for e in body["files"]), adaptation_records=body["metadata"]["editorial_records"],
        approved_playback_stories=body["metadata"]["stories"], selection_mode=body["metadata"]["selection_mode"],
        source_commit_hint=body["metadata"]["source_commit_hint"], bootstrap_sha256=bootstrap["sha256"], start_here_sha256=guide["sha256"],
        receiver_native_test="not performed; requires later user action", credentials_included=False)
    proof = dict(status="ready_for_private_transfer", snapshot=snapshot, files_verified=len(body["files"]),
        payload_bytes=sender["payload_bytes"], package_hash_verification="passed during export", receiver_actions="fresh-folder staging and comparison only",
        github_writes=0, network_calls=0, paid_calls=0, model_servers_started=0, native_project_overwrites=0)
    content = {"START-HERE.md": h.checked_path(bundle, h.object_name(guide["sha256"])).read_bytes(),
        "SENDER-3080.json": h.canonical(sender), "VERIFIED-3080.json": h.canonical(proof)}
    with h.package_lock(bundle):
        h.require(h.read(h.checked_path(bundle, "latest.json"))["snapshot"] == snapshot, "Package pointer changed before receiver notes")
        state = read_note_state(bundle, snapshot)
        new_hashes = {name: h.digest_bytes(data) for name, data in content.items()}
        if state["pending"]:
            pending = state["pending"]
            h.require(pending["new"] == new_hashes, "Pending receiver note content differs; inspect it")
        else:
            for name, data in state["existing"].items():
                archive = h.checked_path(bundle, "receiver-notes/" + state["snapshot"] + "/" + name)
                if not archive.exists():
                    h.atomic_write(archive, data)
            pending = dict(format=NOTE_FORMAT, snapshot=snapshot, previous_snapshot=state["snapshot"],
                old={name: h.digest_bytes(data) for name, data in state["existing"].items()}, new=new_hashes)
            h.atomic_write(h.checked_path(bundle, "receiver-notes.pending.json"), h.canonical(pending))
        for name, data in content.items():
            h.atomic_write(h.checked_path(bundle, name), data)
        h.atomic_write(h.checked_path(bundle, "receiver-notes.json"), h.canonical(dict(format=NOTE_FORMAT, snapshot=snapshot, files=new_hashes)))
        h.checked_path(bundle, "receiver-notes.pending.json").unlink()


def prepare(root, bundle, label, apply=False, source_commit=None):
    root, bundle = Path(root).resolve(), Path(bundle).absolute()
    h.require(bundle != root and not root.is_relative_to(bundle), "Package cannot contain source project")
    plan = build_plan(root, label, source_commit)
    read_note_state(bundle, plan["snapshot"])  # Inspect ownership before changing the package.
    if not apply:
        cost = store_plan(bundle, plan["body"])
        return dict(cost, snapshot=plan["snapshot"], label=label, apply=False, writes=0, network_calls=0,
            adaptation_records=plan["context"]["adaptation_records"], catalogue_ram_restore="passed")
    # The source checkpoint is owned generated data, not an existing user output.
    # Every byte is validated again by export_bundle before object publication.
    generated = dict(plan["generated"])
    generated[plan["frozen_name"]] = h.canonical(plan["body"])
    for name, data in generated.items():
        path = h.checked_path(root, name)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(data)
        else:
            h.require(path.read_bytes() == data, "Checkpoint changed; preserve it")
    report = h.export_bundle(root, bundle, plan["body"], apply=True)
    publish_notes(bundle, plan)
    return dict(report, label=label, adaptation_records=plan["context"]["adaptation_records"], catalogue_ram_restore="passed", receiver_notes="ready")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--label", required=True, help="Explicit version label, e.g. 3080-YYYY-MM-DD-v1; use a new label when data/code changes")
    parser.add_argument("--source-commit", help="Optional local Git commit hint; no Git command is invoked")
    parser.add_argument("--apply", action="store_true", help="Otherwise plan read-only, including RAM-only catalogue validation")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(prepare(args.root, args.bundle, args.label, args.apply, args.source_commit), indent=2))
        return 0
    except (h.HandoffError, OSError, ValueError, KeyError, sqlite3.Error):
        print("Working handoff failed; source contents suppressed. Preserve files and inspect the checkpoint/package locally.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
