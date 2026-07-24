from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from .database import connect


def catalog_status(catalog_path: Path, month: str | None = None) -> dict[str, Any]:
    connection = connect(catalog_path)
    where = "WHERE is_present = 1"
    params: list[object] = []
    if month:
        where += " AND crawl_month = ?"
        params.append(month)

    rows = connection.execute(
        f"""
        SELECT language, crawl_month, quality_flags_json, duplicate_of
          FROM stories
          {where}
        """,
        params,
    ).fetchall()
    version_count = connection.execute("SELECT COUNT(*) FROM story_versions").fetchone()[0]
    run = connection.execute(
        """
        SELECT id, completed_at, files_scanned, stories_seen, inserted, updated,
               unchanged, reappeared, missing, error
          FROM ingest_runs
         ORDER BY id DESC
         LIMIT 1
        """
    ).fetchone()
    card_sql = """
        SELECT COUNT(*)
          FROM stories AS s
         WHERE s.is_present = 1
           AND EXISTS (
               SELECT 1
                 FROM story_cards AS c
                WHERE c.story_id = s.id
                  AND c.content_hash = s.content_hash
           )
    """
    card_params: list[object] = []
    if month:
        card_sql += " AND s.crawl_month = ?"
        card_params.append(month)
    card_count = connection.execute(card_sql, card_params).fetchone()[0]
    connection.close()

    languages = Counter(row["language"] or "unknown" for row in rows)
    months = Counter(row["crawl_month"] or "unknown" for row in rows)
    quality = Counter()
    duplicate_count = 0
    for row in rows:
        quality.update(json.loads(row["quality_flags_json"]))
        duplicate_count += int(row["duplicate_of"] is not None)
    return {
        "scope_month": month,
        "present_stories": len(rows),
        "eligible_unique_stories": len(rows) - duplicate_count,
        "exact_duplicates": duplicate_count,
        "current_story_cards": card_count,
        "story_versions": version_count,
        "languages": dict(sorted(languages.items())),
        "crawl_months": dict(sorted(months.items())),
        "quality_flags": dict(sorted(quality.items())),
        "latest_ingest": dict(run) if run else None,
    }


def story_by_id(connection: sqlite3.Connection, story_id: str) -> sqlite3.Row | None:
    return connection.execute("SELECT * FROM stories WHERE id = ?", (story_id,)).fetchone()
