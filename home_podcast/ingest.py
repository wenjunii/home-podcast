from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .database import connect
from .parser import discover_story_files, parse_story_files
from .records import IngestStats, ParsedStory


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ingest_exports(catalog_path: Path, exports_dir: Path) -> IngestStats:
    exports_dir = exports_dir.resolve()
    if not exports_dir.is_dir():
        raise FileNotFoundError(f"Story exports directory does not exist: {exports_dir}")
    files = discover_story_files(exports_dir)
    if not files:
        raise FileNotFoundError(f"No stories_*.md files found under: {exports_dir}")

    connection = connect(catalog_path)
    started_at = utc_now()
    run_cursor = connection.execute(
        "INSERT INTO ingest_runs(source_root, started_at) VALUES (?, ?)",
        (str(exports_dir), started_at),
    )
    run_id = int(run_cursor.lastrowid)
    connection.commit()

    inserted = updated = unchanged = reappeared = 0
    seen = 0
    try:
        connection.execute("BEGIN")
        for story in parse_story_files(files):
            seen += 1
            action = _upsert_story(
                connection,
                story=story,
                source_root=exports_dir,
                run_id=run_id,
                seen_at=started_at,
            )
            if action == "inserted":
                inserted += 1
            elif action == "updated":
                updated += 1
            elif action == "reappeared":
                reappeared += 1
            else:
                unchanged += 1

        missing_cursor = connection.execute(
            """
            UPDATE stories
               SET is_present = 0
             WHERE source_root = ?
               AND is_present = 1
               AND last_seen_run_id <> ?
            """,
            (str(exports_dir), run_id),
        )
        missing = max(0, missing_cursor.rowcount)
        _refresh_exact_duplicates(connection)
        completed_at = utc_now()
        connection.execute(
            """
            UPDATE ingest_runs
               SET completed_at = ?,
                   files_scanned = ?,
                   stories_seen = ?,
                   inserted = ?,
                   updated = ?,
                   unchanged = ?,
                   reappeared = ?,
                   missing = ?
             WHERE id = ?
            """,
            (
                completed_at,
                len(files),
                seen,
                inserted,
                updated,
                unchanged,
                reappeared,
                missing,
                run_id,
            ),
        )
        connection.commit()
    except Exception as error:
        connection.rollback()
        connection.execute(
            "UPDATE ingest_runs SET completed_at = ?, error = ? WHERE id = ?",
            (utc_now(), f"{type(error).__name__}: {error}", run_id),
        )
        connection.commit()
        raise
    finally:
        connection.close()

    return IngestStats(
        run_id=run_id,
        files_scanned=len(files),
        stories_seen=seen,
        inserted=inserted,
        updated=updated,
        unchanged=unchanged,
        reappeared=reappeared,
        missing=missing,
    )


def _upsert_story(
    connection: sqlite3.Connection,
    *,
    story: ParsedStory,
    source_root: Path,
    run_id: int,
    seen_at: str,
) -> str:
    existing = connection.execute(
        "SELECT record_hash, is_present FROM stories WHERE id = ?", (story.story_id,)
    ).fetchone()
    payload = _story_values(story, source_root, run_id, seen_at)
    if existing is None:
        connection.execute(
            """
            INSERT INTO stories (
                id, language, heading, source_root, source_markdown, source_ordinal,
                source_url, source_file, crawl_dataset, crawl_timestamp, crawl_month,
                match_references_json, accepted_text, story_text, metadata_json,
                quality_flags_json, content_hash, record_hash, duplicate_of,
                first_seen_at, last_seen_at, last_seen_run_id, is_present
            ) VALUES (
                :id, :language, :heading, :source_root, :source_markdown, :source_ordinal,
                :source_url, :source_file, :crawl_dataset, :crawl_timestamp, :crawl_month,
                :match_references_json, :accepted_text, :story_text, :metadata_json,
                :quality_flags_json, :content_hash, :record_hash, NULL,
                :seen_at, :seen_at, :run_id, 1
            )
            """,
            payload,
        )
        _insert_version(connection, story, seen_at)
        return "inserted"

    changed = existing["record_hash"] != story.record_hash
    was_missing = not bool(existing["is_present"])
    connection.execute(
        """
        UPDATE stories
           SET language = :language,
               heading = :heading,
               source_root = :source_root,
               source_markdown = :source_markdown,
               source_ordinal = :source_ordinal,
               source_url = :source_url,
               source_file = :source_file,
               crawl_dataset = :crawl_dataset,
               crawl_timestamp = :crawl_timestamp,
               crawl_month = :crawl_month,
               match_references_json = :match_references_json,
               accepted_text = :accepted_text,
               story_text = :story_text,
               metadata_json = :metadata_json,
               quality_flags_json = :quality_flags_json,
               content_hash = :content_hash,
               record_hash = :record_hash,
               last_seen_at = :seen_at,
               last_seen_run_id = :run_id,
               is_present = 1
         WHERE id = :id
        """,
        payload,
    )
    if changed:
        _insert_version(connection, story, seen_at)
        return "updated"
    if was_missing:
        return "reappeared"
    return "unchanged"


def _story_values(
    story: ParsedStory, source_root: Path, run_id: int, seen_at: str
) -> dict[str, object]:
    return {
        "id": story.story_id,
        "language": story.language,
        "heading": story.heading,
        "source_root": str(source_root),
        "source_markdown": str(story.source_markdown),
        "source_ordinal": story.source_ordinal,
        "source_url": story.source_url,
        "source_file": story.source_file,
        "crawl_dataset": story.crawl_dataset,
        "crawl_timestamp": story.crawl_timestamp,
        "crawl_month": story.crawl_month,
        "match_references_json": json.dumps(story.match_references),
        "accepted_text": story.accepted_text,
        "story_text": story.story_text,
        "metadata_json": json.dumps(story.metadata, ensure_ascii=False, sort_keys=True),
        "quality_flags_json": json.dumps(story.quality_flags),
        "content_hash": story.content_hash,
        "record_hash": story.record_hash,
        "seen_at": seen_at,
        "run_id": run_id,
    }


def _insert_version(
    connection: sqlite3.Connection, story: ParsedStory, seen_at: str
) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO story_versions (
            story_id, record_hash, content_hash, seen_at, accepted_text,
            story_text, metadata_json, quality_flags_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            story.story_id,
            story.record_hash,
            story.content_hash,
            seen_at,
            story.accepted_text,
            story.story_text,
            json.dumps(story.metadata, ensure_ascii=False, sort_keys=True),
            json.dumps(story.quality_flags),
        ),
    )


def _refresh_exact_duplicates(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        UPDATE stories
           SET duplicate_of = CASE
               WHEN id = (
                   SELECT MIN(other.id)
                     FROM stories AS other
                    WHERE other.content_hash = stories.content_hash
                      AND other.is_present = 1
               )
               THEN NULL
               ELSE (
                   SELECT MIN(other.id)
                     FROM stories AS other
                    WHERE other.content_hash = stories.content_hash
                      AND other.is_present = 1
               )
           END
         WHERE is_present = 1
        """
    )
