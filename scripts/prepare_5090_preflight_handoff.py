"""Prepare a local, code-only copy of the reviewed .41 preflight update for later use."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from home_podcast import private_handoff as private

ROOT = Path(__file__).resolve().parents[1]
BASE = "bba2c68fd72b90a731e5e1499f152e177035942f"
HEAD = "c8b477e5943eb915fbe5d201686737dd94d28509"
PATCH_SHA256 = "e664694cd996704a7e2ca6ac2626a017cad79b47149c3f8f8e8a62f4c11c3199"
PATCH_NAME = "3080-show-41-preflight.patch"
NOTE_NAME = "START-HERE.md"
PR_URL = "https://github.com/wenjunii/home-podcast/pull/26"
CHANGES = (
    ("M", "README.md"),
    ("A", "scripts/verify_3080_show_41.py"),
    ("A", "tests/test_verify_3080_show_41.py"),
)
DIFF_OPTIONS = ("--no-ext-diff", "--no-textconv", "--no-color", "--no-renames",
                "--full-index", "--binary", "--src-prefix=a/", "--dst-prefix=b/", "--unified=3")


class PreparationError(ValueError):
    """Only fixed, non-payload diagnostics may reach the caller."""


def require(condition, message):
    if not condition:
        raise PreparationError(message)


def local_git(root, *args):
    env = os.environ.copy()
    for name in ("GIT_DIR", "GIT_COMMON_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
                 "GIT_LITERAL_PATHSPECS", "GIT_GLOB_PATHSPECS", "GIT_NOGLOB_PATHSPECS",
                 "GIT_ICASE_PATHSPECS"):
        env.pop(name, None)
    # A missing object in a partial clone must not cause a lazy fetch.
    env.update(GIT_NO_LAZY_FETCH="1", GIT_ALLOW_PROTOCOL="", GIT_TERMINAL_PROMPT="0")
    result = subprocess.run(
        ["git", "--no-replace-objects", *args], cwd=root, env=env,
        check=False, capture_output=True, timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    require(result.returncode == 0,
            "Local Git check failed; confirm the reviewed commit and ignored output path exist."
            " No automatic fetch was attempted.")
    return result.stdout


def approved_patch(root):
    parent = local_git(root, "rev-parse", "--verify", f"{HEAD}^").decode("ascii").strip()
    require(parent == BASE, "The reviewed PR #26 base did not match.")
    expected = b"".join(f"{status}\0{name}\0".encode("ascii") for status, name in CHANGES)
    names = local_git(root, "diff", "--name-status", "--no-renames", "-z", BASE, HEAD, "--")
    require(names == expected, "The reviewed commit must change exactly the three expected files.")
    paths = [name for _, name in CHANGES]
    local_git(root, "diff", "--check", BASE, HEAD, "--", *paths)
    data = local_git(root, "diff", *DIFF_OPTIONS, BASE, HEAD, "--", *paths)
    require(not private.SECRET.search(data), "Credential-shaped patch content; contents suppressed.")
    require(hashlib.sha256(data).hexdigest() == PATCH_SHA256,
            "The patch differs from the exact reviewed export. Do not transfer or apply it.")
    return data


def handoff_note():
    paths = "\n".join(f"- `{name}`" for _, name in CHANGES)
    return f"""# 5090 handoff: .41 preflight code only

Prepared locally on the sender. This is not authorization to transfer, apply,
or start anything on the 5090. Wait for the user to authorize the sync.

Source: [PR #26]({PR_URL}). Reviewed base `{BASE}`; tested head `{HEAD}`.
The SHA-256 of `{PATCH_NAME}` is:

`{PATCH_SHA256}`

Only these paths change:

{paths}

On the receiver, start by inspecting the current checkout and preserving all
local changes. For the GitHub route, wait until PR #26 is merged, then verify
that it still matches these exact changes. Do not pull unrelated updates.
For offline use, compare the patch digest with the hash above and run
`git apply --check --whitespace=error -- <patch>` in a separate clean review
worktree. Stop if there is any conflict or changed scope. If the exact
changes are already present, do not apply them again.

After the user authorizes staging, use `git apply --whitespace=error -- <patch>`
only in the clean review worktree. Review `git status --short` and
`git diff --check`, and run `py -3.10 -B -m unittest tests.test_verify_3080_show_41`.
Report the staged code and test results before changing a production checkout.
Do not commit or push without separate user direction.

The new verifier applies to the approved 3080 `podcast.41.toe` only. Do not
run it against the 5090 receiver, or copy any show assets, TOEs, credentials,
local settings, or model files. Preserve the .26 receiver and its audio
overlay, .25 rollback, .27 MCP test copy, and any newer receiver projects.
Do not open TouchDesigner, modify MCP/renderer settings, or start models.
The existing 5090 overlay check remains
`py -3.10 -B -m touchdesigner.verify_5090_audio_overlay` in its own checkout.
""".encode()


def write_bundle(target, patch):
    target.mkdir(parents=True, exist_ok=False)
    created = []
    try:
        for name, data in ((PATCH_NAME, patch), (NOTE_NAME, handoff_note())):
            path = target / name
            with path.open("xb") as stream:
                created.append(path)
                stream.write(data)
    except OSError:
        # Roll back only files exclusively opened by this invocation.
        for path in reversed(created):
            path.unlink()
        if not any(target.iterdir()):
            target.rmdir()
        raise


def prepare(root, label, *, apply=False):
    require(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", label)
            and not private.SECRET.search(label.encode("ascii")), "Use a short, non-secret label.")
    root = Path(root).absolute()
    relative = f"work/cross-pc-prep-{label}"
    target = private.checked_path(root, relative)
    require(not target.exists(), "The output already exists. Choose a new label; nothing overwritten.")
    top = local_git(root, "rev-parse", "--show-toplevel").decode("utf-8").strip()
    require(Path(top).resolve() == root.resolve(), "Use the sender's project checkout root.")
    for name in (PATCH_NAME, NOTE_NAME):
        local_git(root, "check-ignore", "--quiet", "--", f"{relative}/{name}")
    patch = approved_patch(root)
    if apply:
        write_bundle(target, patch)
    return {
        "apply": apply, "bundle": relative, "patch_sha256": PATCH_SHA256, "patch_bytes": len(patch),
        "source_pr": 26, "base": BASE, "reviewed_head": HEAD, "paths": [name for _, name in CHANGES],
        "receiver_contacted": False, "network_calls": 0, "local_files_written": 2 if apply else 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="Local sender checkout")
    parser.add_argument("--label", required=True, help="Name for a new local handoff folder")
    parser.add_argument("--apply", action="store_true", help="Write the patch and note locally only")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(prepare(args.root, args.label, apply=args.apply), indent=2))
    except PreparationError as error:
        print(f"Code handoff not prepared: {error}", file=sys.stderr)
        return 2
    except (OSError, ValueError, subprocess.SubprocessError):
        print("Code handoff not prepared; invalid or inaccessible local data (contents suppressed).",
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
