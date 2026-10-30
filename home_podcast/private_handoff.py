"""Private, offline, content-addressed handoffs. Standard library only.

No Git, network, model loading, archive extraction or destination overwrites.
This module also works as the standalone handoff.py shipped inside a package.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import stat
import sys
import uuid

EDITION = "work/storytelling-real-december/continuous-image-hold-136-3080-2026-10-30"
APPROVED = "work/storytelling-real-december/approved-136-five-second-3080-2026-10-30"
TOE = "podcast.40.toe"
FORMAT = "recovered-homes-private-handoff-v1"
TEXT = {".py", ".ps1", ".json", ".jsonl", ".md", ".txt", ".toml", ".html", ".srt", ".vtt", ".yml", ".yaml", ".ini", ".cfg"}
HEX = re.compile(r"[0-9a-f]{64}\Z")
SECRET = re.compile(rb"(?:sk-[A-Za-z0-9_-]{20,}|sk_[a-fA-F0-9]{32,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")
RESERVED = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?\Z", re.I)


class HandoffError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise HandoffError(message)


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def safe_name(name):
    require(isinstance(name, str) and bool(name), "Empty/non-string package path")
    require("\\" not in name and ":" not in name and not any(c in name for c in '\x00<>"|?*'), "Unsafe package path")
    parts = name.split("/")
    require(not PurePosixPath(name).is_absolute() and not PureWindowsPath(name).drive, "Absolute package path")
    for part in parts:
        require(part not in ("", ".", "..") and part == part.rstrip(" .") and not RESERVED.fullmatch(part), "Unsafe path component")
        low = part.casefold()
        require(low not in {".git", ".venv", ".ssh", ".aws", ".azure", ".codex", ".gemini", "__pycache__", "node_modules", "auth.json", "credentials.json"}
                and not low.startswith(".env") and not low.endswith((".pem", ".key")), "Excluded private/cache path")
    return name


def checked_path(root, name):
    """Reject traversal, symlinks and Windows junctions, including parent links."""
    safe_name(name)
    root = Path(root).absolute()
    current = Path(root.anchor)
    for part in root.parts[1:] + PurePosixPath(name).parts:
        current /= part
        if current.exists() or current.is_symlink():
            attrs = current.lstat()
            require(not stat.S_ISLNK(attrs.st_mode) and not (getattr(attrs, "st_file_attributes", 0) & 0x400), "Symlink/reparse paths are not supported")
    require(current.resolve().is_relative_to(root.resolve()), "Path escaped its root")
    return current


def scan(path, name):
    """Fail closed without printing matched bytes or credential values."""
    suffix = Path(name).suffix.lower()
    if suffix not in TEXT | {".toe"}:
        return
    data = Path(path).read_bytes()
    found = bool(SECRET.search(data))
    if suffix == ".toe":
        for encoding in ("utf-16-le", "utf-16-be"):
            found |= bool(SECRET.search(data.decode(encoding, errors="ignore").encode("utf-8")))
    require(not found, "Credential-shaped content: " + name + " (contents suppressed)")
    if suffix == ".json":
        def walk(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if str(key).casefold() in {"api_key", "apikey", "access_token", "refresh_token", "client_secret", "password", "authorization"}:
                        require(item in (None, "", False), "Nonempty credential field: " + name + " (contents suppressed)")
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)
        walk(read(path))


def _add_tree(root, selected, folder, suffixes, role):
    base = checked_path(root, folder)
    require(base.is_dir(), "Missing required directory: " + folder)
    for path in sorted(base.rglob("*")):
        if path.is_file() and path.suffix.lower() in suffixes and "__pycache__" not in path.parts:
            name = path.relative_to(root).as_posix()
            checked_path(root, name)
            selected.setdefault(name, set()).add(role)


def runtime_closure(root, seeds):
    """Follow literal project-root Python dependencies without executing code.

    The TD base modules and same-folder imports are included separately. This
    captures the edition's explicit importlib/exec chains under work/.
    """
    pending = list(seeds)
    result = set()
    while pending:
        name = pending.pop()
        if name in result:
            continue
        path = checked_path(root, name)
        require(path.is_file(), "Missing runtime dependency: " + name)
        result.add(name)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=name)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            value = node.value
            if value.endswith(".py") and value.startswith(("work/", "touchdesigner/", "home_podcast/", "scripts/")):
                safe_name(value)
                pending.append(value)
    return result


def build_selection(root, editable=True):
    root = Path(root).resolve()
    selected = {}
    expected = {}

    def add(name, role, checksum=None):
        path = checked_path(root, name)
        require(path.is_file(), "Missing required file: " + name)
        selected.setdefault(name, set()).add(role)
        if checksum:
            require(not expected.get(name) or expected[name] == checksum, "Conflicting source bindings")
            expected[name] = checksum

    manifest = read(checked_path(root, EDITION + "/playlist.json"))
    save = read(checked_path(root, EDITION + "/native-save-verification.json"))
    require(save["new_toe"] == TOE and manifest["story_count"] == len(manifest["stories"]) == 136, "Not the approved .40/136-story edition")
    ids = [s["narration_id"] for s in manifest["stories"]]
    require(len(set(ids)) == 136, "Repeated active story ID")
    add(TOE, "licensed_private_3080_project", save["new_toe_sha256"])
    add(EDITION + "/playlist.json", "active_playlist")
    for kind, name in manifest["audio"].items():
        add(name, "playlist_" + kind, manifest["audio_sha256"][kind])
    for extension in ("srt", "vtt"):
        add("audio/storytelling-real-december/approved-136-five-second-3080-2026-10-30/playlist-captions." + extension, "reviewed_playlist_captions")
    seeds = {EDITION + "/install.py"}
    for entry in manifest["plans"].values():
        add(entry["path"], "reviewed_visuals_and_captions", entry["sha256"])
        plan = read(root / entry["path"])
        require(len(plan["scenes"]) == 619 and len(plan["captions"]) == 2862 and plan["duration_ms"] == manifest["duration_ms"], "Changed visual scope/clock")
        require([s["narration_id"] for s in plan["playlist_stories"]] == ids, "Changed visual story order")
        seeds.update((plan["sequencer_module"], plan["controller_module"]))
    seeds.add("work/storytelling-real-december/expanded-playlist-136-3080-2026-10-30/offline_show_control_callbacks.py")
    for name in runtime_closure(root, seeds):
        add(name, "runtime_dependency")
    # Shared source is a working-tree snapshot, including uncommitted changes,
    # not a git archive of an older HEAD. No .git history or provider secrets.
    for folder in ("home_podcast", "scripts", "touchdesigner", "tests"):
        _add_tree(root, selected, folder, {".py", ".ps1"}, "project_code")
    for folder in ("config", "contracts", "prompts", "docs"):
        _add_tree(root, selected, folder, TEXT, "configuration_or_documentation")
    for name in ("AGENTS.md", "README.md", "LICENSE", "pyproject.toml", ".gitignore", ".gitattributes", "storytelling.real-december.json", "podcast.json"):
        add(name, "project_configuration")
    # Receipts are preserved as historical evidence. Their protected-input
    # inventories do NOT authorize exporting every legacy TOE or old cache.
    for folder in (EDITION, EDITION.replace("continuous-image-hold", "interpolated"), APPROVED):
        for path in (root / folder).glob("*.json"):
            add(path.relative_to(root).as_posix(), "edition_receipt")
    _add_tree(root, selected, "work/storytelling-real-december/local-audio/approvals", {".json"}, "existing_human_approval")
    for name in (
        "expanded-playlist-136-3080-2026-10-30/approval.json",
        "continuous-crossfades-3080-2026-10-30/caption-98-approval.json",
        "caption-review-98-2026-10-30/human-approval.json",
        "visual-approved-selection-91-2026-10-30/human-approval.json",
        "ambient-detail-143-v1-2026-10-30/authorization.json",
        "ambient-recheck-136-2026-10-30/user-direction.json",
        "five-second-visuals-136-3080-2026-10-30/transition-authorization.json",
        "remaining-322-2026-10-29/first-100-listening-approval.json",
        "remaining-322-2026-10-29/cohort-listening-approval-verification.json",
        "remaining-322-2026-10-29/held-five-repair/listening-approval.json",
        "remaining-322-2026-10-29/first100-ambient/listening-approval.json",
    ):
        add("work/storytelling-real-december/" + name, "existing_human_approval_or_authorization")
    if editable:
        collection = read(root / APPROVED / "collection.json")
        require([s["narration_id"] for s in collection["stories"]] == ids, "Editable collection/order mismatch")
        add(APPROVED + "/collection.json", "approved_per_story_media_bindings")
        for story in collection["stories"]:
            for kind, name in story["audio"].items():
                add(name, "approved_story_" + kind, story["audio_sha256"][kind])
            directory = "narrations/real-december/" + story["narration_id"]
            for required in ("source-job.json", "adaptation.json", "personal-story-review.json", "manifest.json"):
                add(directory + "/" + required, "frozen_story_and_personal_review")
            _add_tree(root, selected, directory, TEXT, "selected_story_editorial_history")
        for path in sorted((root / "data/exports").glob("stories_*.md")):
            add(path.relative_to(root).as_posix(), "original_story_exports")
    return selected, expected, dict(edition="136-story-.40", toe=TOE, profile="3080_safe", playlist=EDITION + "/playlist.json",
        stories=136, scenes_per_path=619, captions=2862, duration_ms=manifest["duration_ms"], editable=editable,
        excluded="Credentials, Git history, model weights/environments, old TOEs, render caches and nonselected story media. Historical review pages/caches are not a full archive.")


def inventory(root, selected, expected=None, metadata=None):
    entries = []
    for name in sorted(selected):
        path = checked_path(root, name)
        require(path.is_file(), "Missing selected file: " + name)
        scan(path, name)
        checksum = sha(path)
        require(not (expected or {}).get(name) or checksum == expected[name], "Changed approved file: " + name)
        entries.append(dict(path=name, sha256=checksum, size=path.stat().st_size, roles=sorted(selected[name])))
    body = dict(format=FORMAT, metadata=metadata or {}, files=entries)
    validate_manifest(body)
    return body


def validate_manifest(body):
    require(isinstance(body, dict) and body.get("format") == FORMAT, "Unsupported package format")
    require(isinstance(body.get("metadata"), dict) and isinstance(body.get("files"), list) and body["files"], "Malformed manifest")
    seen = set()
    for entry in body["files"]:
        require(isinstance(entry, dict), "Malformed file entry")
        name = safe_name(entry.get("path"))
        require(name.casefold() != "private-handoff-receipt.json", "Reserved import receipt path")
        require(name.casefold() not in seen, "Duplicate/case-colliding package paths")
        seen.add(name.casefold())
        require(isinstance(entry.get("sha256"), str) and HEX.fullmatch(entry["sha256"]), "Invalid file digest")
        require(type(entry.get("size")) is int and entry["size"] >= 0, "Invalid file size")
        require(isinstance(entry.get("roles"), list) and all(isinstance(x, str) for x in entry["roles"]), "Invalid roles")
        require(Path(name).suffix.lower() not in {".tox", ".sqlite3", ".gz", ".pem", ".key"}, "Excluded file type")
        require(Path(name).suffix.lower() != ".toe" or name == TOE, "Only the selected private 3080 TOE may transfer")
    for name in seen:
        parts = name.split("/")
        require(not any("/".join(parts[:i]) in seen for i in range(1, len(parts))), "File/directory path collision")
    return body


@contextmanager
def package_lock(bundle):
    path = checked_path(bundle, "handoff.lock")
    try:
        stream = path.open("x", encoding="utf-8")
    except FileExistsError:
        raise HandoffError("Package is locked; inspect the existing export before continuing") from None
    try:
        stream.write(str(os.getpid()));stream.close()
        yield
    finally:
        stream.close()
        path.unlink()


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".partial")
    try:
        with temp.open("xb") as stream:
            stream.write(data)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def _copy_verified(source, target, entry):
    """Publish only a complete hash-checked file, never a partial destination."""
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(target.name + "." + uuid.uuid4().hex + ".partial")
    try:
        with Path(source).open("rb") as incoming, temp.open("xb") as outgoing:
            shutil.copyfileobj(incoming, outgoing, 1024 * 1024)
        require(temp.stat().st_size == entry["size"] and sha(temp) == entry["sha256"], "Source changed during transfer: " + entry["path"])
        require(not target.exists(), "Destination appeared during transfer; preserve it")
        if os.name == "nt":
            # Windows rename fails rather than replacing an existing target.
            os.rename(temp, target)
        else:
            # link is an atomic exclusive publication on POSIX filesystems.
            os.link(temp, target)
            temp.unlink()
    finally:
        if temp.exists():
            temp.unlink()


def object_name(checksum):
    require(bool(HEX.fullmatch(checksum)), "Invalid object digest")
    return "objects/" + checksum[:2] + "/" + checksum


def load_bundle(bundle, snapshot=None):
    bundle = Path(bundle).resolve()
    if snapshot is None:
        latest = read(checked_path(bundle, "latest.json"))
        snapshot = latest.get("snapshot")
    require(isinstance(snapshot, str) and bool(HEX.fullmatch(snapshot)), "Invalid snapshot identifier")
    path = checked_path(bundle, "snapshots/" + snapshot + ".json")
    data = path.read_bytes()
    require(digest_bytes(data) == snapshot, "Manifest digest mismatch")
    return validate_manifest(json.loads(data)), snapshot


def verify_bundle(bundle, snapshot=None):
    body, snapshot = load_bundle(bundle, snapshot)
    unique = {}
    for entry in body["files"]:
        old = unique.setdefault(entry["sha256"], entry["size"])
        require(old == entry["size"], "Conflicting object sizes")
        path = checked_path(bundle, object_name(entry["sha256"]))
        require(path.is_file() and path.stat().st_size == entry["size"], "Missing/truncated package object: " + entry["path"])
        scan(path, entry["path"])
    for checksum in unique:
        require(sha(checked_path(bundle, object_name(checksum))) == checksum, "Corrupt package object (digest only): " + checksum)
    # The standalone launcher follows the newest tool version. Older snapshots
    # still verify against their own immutable source object, not that launcher.
    return dict(passed=True, snapshot=snapshot, files=len(body["files"]), unique_objects=len(unique), bytes=sum(e["size"] for e in body["files"]), network_calls=0)


def export_bundle(root, bundle, body, apply=False):
    validate_manifest(body)
    root, bundle = Path(root).resolve(), Path(bundle).absolute()
    require(bundle != root and not root.is_relative_to(bundle), "Package cannot contain the source project")
    marker_path = checked_path(bundle, "private-handoff-package.json")
    marker = dict(format=FORMAT, allowed_bootstrap_sha256=[])
    if bundle.exists() and any(bundle.iterdir()):
        require(not checked_path(bundle, "handoff.lock").exists(), "Package is locked; inspect the existing export before continuing")
        require(marker_path.is_file(), "Use an empty folder or an existing private handoff package")
        marker = read(marker_path)
        require(marker.get("format") == FORMAT and isinstance(marker.get("allowed_bootstrap_sha256"), list), "Invalid package marker")
        launcher = checked_path(bundle, "handoff.py")
        if launcher.exists():
            require(sha(launcher) in marker["allowed_bootstrap_sha256"], "Standalone tool was locally edited; preserve it and use a new package folder")
    snapshot = digest_bytes(canonical(body))
    unique = {entry["sha256"]: entry for entry in body["files"]}
    pending = []
    for entry in unique.values():
        source = checked_path(root, entry["path"])
        require(source.is_file() and sha(source) == entry["sha256"], "Source changed since planning: " + entry["path"])
        scan(source, entry["path"])
        target = checked_path(bundle, object_name(entry["sha256"]))
        if target.exists():
            require(target.is_file() and target.stat().st_size == entry["size"] and sha(target) == entry["sha256"], "Existing package object is corrupt; preserve it for inspection")
        else:
            pending.append(entry)
    report = dict(snapshot=snapshot, files=len(body["files"]), unique_objects=len(unique), new_objects=len(pending),
        reused_objects=len(unique)-len(pending), copy_bytes=sum(e["size"] for e in pending), apply=apply, network_calls=0)
    if not apply:
        return report
    bundle.mkdir(parents=True, exist_ok=True)
    require(shutil.disk_usage(bundle).free > report["copy_bytes"] + 16*1024*1024, "Insufficient package disk space")
    with package_lock(bundle):
        bootstrap = next((e for e in body["files"] if e["path"] == "home_podcast/private_handoff.py"), None)
        if bootstrap and bootstrap["sha256"] not in marker["allowed_bootstrap_sha256"]:
            marker["allowed_bootstrap_sha256"].append(bootstrap["sha256"])
        # Register immutable tool versions before publication so an interrupted
        # update can resume without treating our completed launcher as foreign.
        atomic_write(marker_path, canonical(marker))
        for entry in pending:
            _copy_verified(checked_path(root, entry["path"]), checked_path(bundle, object_name(entry["sha256"])), entry)
        if bootstrap:
            atomic_write(checked_path(bundle, "handoff.py"), checked_path(bundle, object_name(bootstrap["sha256"])).read_bytes())
        manifest_path = checked_path(bundle, "snapshots/" + snapshot + ".json")
        data = canonical(body)
        if manifest_path.exists():
            require(manifest_path.read_bytes() == data, "Existing immutable snapshot differs")
        else:
            atomic_write(manifest_path, data)
        verify_bundle(bundle, snapshot)
        atomic_write(checked_path(bundle, "latest.json"), canonical(dict(snapshot=snapshot, format=FORMAT)))
    return report


def import_bundle(bundle, target, snapshot=None, apply=False):
    verification = verify_bundle(bundle, snapshot)
    body, snapshot = load_bundle(bundle, verification["snapshot"])
    target, bundle = Path(target).absolute(), Path(bundle).resolve()
    require(target != bundle and not target.is_relative_to(bundle) and not bundle.is_relative_to(target), "Import target and package must not overlap")
    require(target != Path(target.anchor) and target.resolve() != Path.home().resolve(), "Use a dedicated project directory")
    new = [];same = [];conflicts = []
    # A missing file whose ancestor is an existing file is also a conflict;
    # detect it before creating any directories or copying any payload.
    for entry in body["files"]:
        path = checked_path(target, entry["path"])
        require(all(not p.exists() or p.is_dir() for p in path.parents if p.is_relative_to(target)), "Import parent is a file; nothing copied")
        if path.exists():
            if path.is_file() and path.stat().st_size == entry["size"] and sha(path) == entry["sha256"]:
                same.append(entry)
            else:
                conflicts.append(entry["path"])
        else:
            new.append(entry)
    report = dict(snapshot=snapshot, files=len(body["files"]), copy_files=len(new), unchanged_files=len(same),
        copy_bytes=sum(e["size"] for e in new), conflicts=conflicts, apply=apply, overwrites=0, network_calls=0)
    require(not conflicts, "Import conflicts; nothing copied. Use a fresh project folder. Conflicting files: " + ", ".join(conflicts[:8]))
    receipt_name = "private-handoff-receipt.json"
    receipt = dict(format=FORMAT, snapshot=snapshot, metadata=body["metadata"], files=body["files"], no_overwrites=True)
    receipt_path = checked_path(target, receipt_name)
    if receipt_path.exists():
        require(receipt_path.read_bytes() == canonical(receipt), "Existing import receipt belongs to another snapshot; use a fresh folder")
    if not apply:
        return report
    target.mkdir(parents=True, exist_ok=True)
    require(shutil.disk_usage(target).free > report["copy_bytes"] + 16*1024*1024, "Insufficient import disk space")
    for entry in new:
        _copy_verified(checked_path(bundle, object_name(entry["sha256"])), checked_path(target, entry["path"]), entry)
    if not receipt_path.exists():
        atomic_write(receipt_path, canonical(receipt))
    report["verified"] = verify_target(target)["passed"]
    return report


def verify_target(target):
    receipt = read(checked_path(target, "private-handoff-receipt.json"))
    body = dict(format=receipt["format"], metadata=receipt["metadata"], files=receipt["files"])
    validate_manifest(body)
    require(digest_bytes(canonical(body)) == receipt["snapshot"], "Import receipt digest mismatch")
    for entry in body["files"]:
        path = checked_path(target, entry["path"])
        require(path.is_file() and path.stat().st_size == entry["size"] and sha(path) == entry["sha256"], "Restored file changed/missing: " + entry["path"])
        scan(path, entry["path"])
    return dict(passed=True, snapshot=receipt["snapshot"], files=len(body["files"]), network_calls=0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "export"):
        command = commands.add_parser(name)
        command.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
        command.add_argument("--playback-only", action="store_true", help="Omit individual story media and editorial history")
        if name == "export":
            command.add_argument("--bundle", type=Path, required=True)
            command.add_argument("--apply", action="store_true", help="Otherwise report the dry run only")
    command = commands.add_parser("verify")
    command.add_argument("--bundle", type=Path, required=True)
    command.add_argument("--snapshot")
    command = commands.add_parser("import")
    command.add_argument("--bundle", type=Path, required=True)
    command.add_argument("--target", type=Path, required=True)
    command.add_argument("--snapshot")
    command.add_argument("--apply", action="store_true")
    command = commands.add_parser("verify-target")
    command.add_argument("--target", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command in ("plan", "export"):
            selection, expected, metadata = build_selection(args.root, editable=not args.playback_only)
            body = inventory(args.root, selection, expected, metadata)
            if args.command == "plan":
                result = dict(files=len(body["files"]), bytes=sum(e["size"] for e in body["files"]), metadata=metadata, credential_scan="passed", writes=0)
            else:
                result = export_bundle(args.root, args.bundle, body, args.apply)
        elif args.command == "verify":
            result = verify_bundle(args.bundle, args.snapshot)
        elif args.command == "import":
            result = import_bundle(args.bundle, args.target, args.snapshot, args.apply)
        else:
            result = verify_target(args.target)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (HandoffError, OSError, KeyError, json.JSONDecodeError) as error:
        # Never expose unknown JSON values, credential contents or arbitrary
        # source text through a traceback. HandoffError messages are sanitized.
        print(str(error) if isinstance(error, HandoffError) else type(error).__name__ + ": handoff failed; inspect files locally", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
