"""Safely synchronize only stories_*.md files from the extractor project."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import shutil
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from home_podcast.parser import discover_story_files, parse_story_files


DEFAULT_SOURCE = ROOT.parent / "cc-home-extractor" / "data" / "exports"
DEFAULT_DESTINATION = ROOT / "data" / "exports"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot(root: Path) -> dict[str, Any]:
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Story export directory does not exist: {root}")
    files = discover_story_files(root)
    if not files:
        raise FileNotFoundError(f"No stories_*.md files found under: {root}")
    records = list(parse_story_files(files))
    if not records:
        raise ValueError(f"No story records could be parsed under: {root}")

    by_id: dict[str, list[Any]] = defaultdict(list)
    content_counts: Counter[str] = Counter()
    for record in records:
        by_id[record.story_id].append(record)
        content_counts[record.content_hash] += 1
    collisions = {story_id: values for story_id, values in by_id.items() if len(values) > 1}
    if collisions:
        first = sorted(collisions)[0]
        raise ValueError(f"Duplicate story ID {first!r} found under: {root}")

    return {
        "root": root,
        "files": {path.name: path for path in files},
        "file_hashes": {path.name: file_sha256(path) for path in files},
        "records": records,
        "by_id": {story_id: values[0] for story_id, values in by_id.items()},
        "languages": dict(sorted(Counter(record.language for record in records).items())),
        "crawl_months": dict(
            sorted(Counter(record.crawl_month or "unknown" for record in records).items())
        ),
        "quality_flags": dict(
            sorted(
                Counter(
                    flag
                    for record in records
                    for flag in record.quality_flags
                ).items()
            )
        ),
        "exact_duplicates": sum(count - 1 for count in content_counts.values()),
    }


def compare_snapshots(source: dict[str, Any], destination: dict[str, Any]) -> dict[str, Any]:
    source_ids = set(source["by_id"])
    destination_ids = set(destination["by_id"])
    shared = source_ids & destination_ids
    content_changed = [
        story_id
        for story_id in shared
        if source["by_id"][story_id].content_hash
        != destination["by_id"][story_id].content_hash
    ]
    record_changed = [
        story_id
        for story_id in shared
        if source["by_id"][story_id].record_hash
        != destination["by_id"][story_id].record_hash
    ]
    return {
        "new_story_ids": len(source_ids - destination_ids),
        "removed_story_ids": len(destination_ids - source_ids),
        "shared_story_ids": len(shared),
        "shared_content_changed": len(content_changed),
        "shared_record_changed": len(record_changed),
        "new_files": sorted(set(source["files"]) - set(destination["files"])),
        "stale_files": sorted(set(destination["files"]) - set(source["files"])),
        "changed_files": sorted(
            name
            for name in set(source["files"]) & set(destination["files"])
            if source["file_hashes"][name] != destination["file_hashes"][name]
        ),
    }


def atomic_copy(source: Path, destination: Path) -> None:
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        shutil.copy2(source, temporary)
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def sync_story_exports(
    source_root: Path,
    destination_root: Path,
    *,
    apply: bool = False,
    prune: bool = False,
) -> dict[str, Any]:
    source = snapshot(source_root)
    destination = snapshot(destination_root)
    if source["root"] == destination["root"]:
        raise ValueError("Source and destination story directories must be different")
    comparison = compare_snapshots(source, destination)
    if apply and comparison["stale_files"] and not prune:
        raise ValueError(
            "Destination contains stale stories_*.md files; rerun with --prune "
            "only after reviewing the dry-run report"
        )

    copied: list[str] = []
    removed: list[str] = []
    if apply:
        destination["root"].mkdir(parents=True, exist_ok=True)
        for name, source_path in source["files"].items():
            destination_path = destination["root"] / name
            if (
                not destination_path.is_file()
                or file_sha256(destination_path) != source["file_hashes"][name]
            ):
                atomic_copy(source_path, destination_path)
                copied.append(name)
        if prune:
            for name in comparison["stale_files"]:
                stale_path = destination["root"] / name
                stale_path.unlink()
                removed.append(name)

        verified = snapshot(destination["root"])
        if source["file_hashes"] != verified["file_hashes"]:
            raise RuntimeError("Destination story files do not match the source snapshot")
        if set(source["by_id"]) != set(verified["by_id"]):
            raise RuntimeError("Destination story IDs do not match the source snapshot")
        destination_after = len(verified["records"])
    else:
        destination_after = len(destination["records"])

    return {
        "applied": apply,
        "source_files": len(source["files"]),
        "source_stories": len(source["records"]),
        "source_languages": source["languages"],
        "source_crawl_months": source["crawl_months"],
        "source_quality_flags": source["quality_flags"],
        "source_exact_duplicates": source["exact_duplicates"],
        "destination_stories_before": len(destination["records"]),
        "destination_stories_after": destination_after,
        **comparison,
        "copied_files": copied,
        "pruned_files": removed,
        "network_calls": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Dry-run or synchronize stories_*.md only. matches files, compressed "
            "JSONL, credentials, and all other extractor artifacts are excluded."
        )
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Remove destination stories_*.md files absent from the source; requires --apply",
    )
    args = parser.parse_args()
    if args.prune and not args.apply:
        parser.error("--prune requires --apply")
    report = sync_story_exports(
        args.source,
        args.destination,
        apply=args.apply,
        prune=args.prune,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
