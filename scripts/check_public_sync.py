"""Read-only public-sync gate over actual Git blobs, never working-copy guesses.

Default: audit staged additions/modifications. With --base REF, audit every
new commit's changed blobs, including content deleted again in a later commit.
No push, commit, credentials, model loading or network calls.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {".gitignore", ".gitattributes", "AGENTS.md", "README.md", "LICENSE", "pyproject.toml", "podcast.json", "storytelling.real-december.json"}
PREFIXES = ("home_podcast/", "scripts/", "tests/", "config/", "contracts/", "prompts/", "docs/", "touchdesigner/", ".github/")
EXTENSIONS = {".py", ".ps1", ".md", ".txt", ".json", ".jsonl", ".toml", ".yml", ".yaml"}
SECRET = re.compile(rb"(?:sk-[A-Za-z0-9_-]{20,}|sk_[a-fA-F0-9]{32,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")
CREDENTIAL_FIELDS = {"api_key", "apikey", "access_token", "refresh_token", "client_secret", "password", "authorization", "secret_key", "api_secret", "aws_secret_access_key"}


def git(root, *args, input_data=None):
    result = subprocess.run(["git", "--literal-pathspecs", *args], cwd=root, input=input_data,
        capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise ValueError("Git inspection failed; details suppressed")
    return result.stdout


def entries_from_tree(data, staged=False):
    entries = {}
    for row in data.split(b"\0"):
        if not row:
            continue
        header, name = row.split(b"\t", 1)
        fields = header.split(b" ")
        mode, oid = (fields[0], fields[1]) if staged else (fields[0], fields[2])
        if staged and fields[2] != b"0":
            mode = b"unmerged"
        entries[name.decode("utf-8")] = (mode, oid.decode("ascii"))
    return entries


def read_blobs(root, oids):
    """One bounded Git batch, rather than two processes for every source file."""
    ordered = sorted(set(oids))
    if not ordered:
        return {}
    if any(not re.fullmatch(r"[0-9a-f]{40,64}", oid) for oid in ordered):
        raise ValueError("Invalid blob identifier")
    request = ("\n".join(ordered)+"\n").encode("ascii")
    headers = git(root, "cat-file", "--batch-check", input_data=request).splitlines()
    if len(headers) != len(ordered):
        raise ValueError("Truncated Git size check")
    for oid, row in zip(ordered, headers):
        fields = row.split(b" ")
        if len(fields) != 3 or fields[0].decode("ascii") != oid or fields[1] != b"blob" or not 0 <= int(fields[2]) <= 5*1024*1024:
            raise ValueError("Invalid/oversized public source blob; payload not read")
    data = git(root, "cat-file", "--batch", input_data=request)
    blobs = {};cursor = 0
    for oid in ordered:
        end = data.find(b"\n", cursor)
        if end < 0:
            raise ValueError("Truncated Git batch")
        header = data[cursor:end].split(b" ")
        if len(header) != 3 or header[0].decode("ascii") != oid or header[1] != b"blob":
            raise ValueError("Unexpected Git object")
        length = int(header[2]);cursor = end+1
        payload = data[cursor:cursor+length];cursor += length
        if len(payload) != length or data[cursor:cursor+1] != b"\n":
            raise ValueError("Truncated Git blob")
        blobs[oid] = payload;cursor += 1
    if cursor != len(data):
        raise ValueError("Unexpected Git batch tail")
    return blobs


def allowed_path(name):
    parts = name.split("/")
    return (not SECRET.search(name.encode("utf-8")) and "\\" not in name and ":" not in name
        and all(p not in ("", ".", "..", ".git") and not p.casefold().startswith(".env") for p in parts)
        and (name in ROOT_FILES or name.startswith(PREFIXES) and Path(name).suffix in EXTENSIONS))


def credential_field(value):
    if isinstance(value, dict):
        return any((str(k).casefold() in CREDENTIAL_FIELDS and v not in (None, "", False)) or credential_field(v) for k, v in value.items())
    if isinstance(value, list):
        return any(credential_field(v) for v in value)
    return False


def audit(root=ROOT, base=None):
    root = Path(root).resolve()
    commits = []
    if base is None:
        names = git(root, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
        tree = entries_from_tree(git(root, "ls-files", "--stage", "-z"), staged=True)
        scopes = [(names, tree)]
    else:
        resolved = git(root, "rev-parse", "--verify", "--end-of-options", base + "^{commit}").decode().strip()
        if not re.fullmatch(r"[0-9a-f]{40,64}", resolved):
            raise ValueError("Invalid base revision")
        commits = git(root, "rev-list", "--reverse", resolved + "..HEAD").decode().splitlines()
        scopes = [(git(root, "diff-tree", "--root", "--no-commit-id", "-r", "-m", "--name-only", "--diff-filter=ACMR", "-z", commit),
            entries_from_tree(git(root, "ls-tree", "-r", "-z", commit))) for commit in commits]
    scanned = 0; total = 0; findings = []; selected = []
    for names, tree in scopes:
        for raw_name in names.split(b"\0"):
            if not raw_name:
                continue
            name = raw_name.decode("utf-8")
            if not allowed_path(name):
                findings.append(dict(path=name if not SECRET.search(raw_name) else "[credential-shaped filename suppressed]", issue="not_in_public_code_scope"))
                continue
            # Mode checks prevent symlinks and submodules from evading the blob gate.
            mode, oid = tree[name]
            if mode not in (b"100644", b"100755"):
                findings.append(dict(path=name, issue="not_a_regular_source_file"));continue
            selected.append((name, oid))
    blobs = read_blobs(root, [oid for _, oid in selected])
    for name, oid in selected:
        data = blobs[oid]
        scanned += 1; total += len(data)
        issue = None
        if len(data) > 5 * 1024 * 1024:
            issue = "oversized_public_source_file"
        elif SECRET.search(data):
            issue = "credential_shaped_content"
        else:
            try:
                text = data.decode("utf-8")
                if "\0" in text:
                    issue = "binary_content"
                elif name.endswith(".json") and credential_field(json.loads(text)):
                    issue = "nonempty_credential_field"
            except (UnicodeDecodeError, json.JSONDecodeError):
                issue = "invalid_text_or_json"
        if issue:
            findings.append(dict(path=name, issue=issue))
    return dict(passed=not findings, scope="staged" if base is None else "all_new_commit_blobs", commits=len(commits),
        blobs_scanned=scanned, bytes_scanned=total, findings=findings, credential_contents_printed=False, network_calls=0, writes=0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--base", help="Audit every new commit after this local base ref")
    args = parser.parse_args(argv)
    try:
        result = audit(args.root, args.base)
        print(json.dumps(result, indent=2))
        return 0 if result["passed"] else 1
    except (OSError, ValueError, KeyError):
        print("Public sync audit failed; no contents printed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
