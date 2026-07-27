from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .config import ProjectConfig
from .database import connect


def export_analysis_packets(
    config: ProjectConfig,
    output_path: Path,
    *,
    month: str | None = None,
    cohort_path: Path | None = None,
    include_existing: bool = False,
    limit: int | None = None,
) -> int:
    themes = config.load_themes()["themes"]
    cohort_hashes: dict[str, str] | None = None
    if cohort_path is not None:
        cohort = json.loads(cohort_path.read_text(encoding="utf-8"))
        if cohort.get("kind") != "crawl_month_cohort":
            raise ValueError(f"Not a crawl-month cohort manifest: {cohort_path}")
        if month is not None and cohort.get("crawl_month") != month:
            raise ValueError(
                f"Cohort month {cohort.get('crawl_month')} does not match {month}"
            )
        cohort_hashes = {
            item["story_id"]: item["content_hash"] for item in cohort["stories"]
        }
        if not cohort_hashes:
            raise ValueError(f"Cohort contains no stories: {cohort_path}")
        if len(cohort_hashes) != len(cohort["stories"]):
            raise ValueError(f"Cohort contains duplicate story IDs: {cohort_path}")

    connection = connect(config.catalog_path)
    conditions = ["s.is_present = 1", "s.duplicate_of IS NULL"]
    params: list[object] = []
    if month:
        conditions.append("s.crawl_month = ?")
        params.append(month)
    if cohort_hashes is not None:
        placeholders = ",".join("?" for _ in cohort_hashes)
        current_rows = connection.execute(
            f"""
            SELECT id, content_hash
              FROM stories
             WHERE is_present = 1
               AND duplicate_of IS NULL
               AND id IN ({placeholders})
            """,
            list(cohort_hashes),
        ).fetchall()
        current_hashes = {row["id"]: row["content_hash"] for row in current_rows}
        missing_or_changed = [
            story_id
            for story_id, content_hash in cohort_hashes.items()
            if current_hashes.get(story_id) != content_hash
        ]
        if missing_or_changed:
            connection.close()
            preview = ", ".join(missing_or_changed[:5])
            raise ValueError(
                "Frozen cohort stories changed or disappeared; "
                f"first affected IDs: {preview}"
            )
        conditions.append(f"s.id IN ({placeholders})")
        params.extend(cohort_hashes)
    if not include_existing:
        conditions.append(
            """
            NOT EXISTS (
                SELECT 1 FROM story_cards AS c
                 WHERE c.story_id = s.id AND c.content_hash = s.content_hash
            )
            """
        )
    sql = f"""
        SELECT s.*
          FROM stories AS s
         WHERE {' AND '.join(conditions)}
         ORDER BY s.crawl_timestamp, s.language, s.id
    """
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    rows = connection.execute(sql, params).fetchall()
    connection.close()
    if cohort_hashes is not None:
        for row in rows:
            if cohort_hashes[row["id"]] != row["content_hash"]:
                raise ValueError(
                    f"Cohort story changed after snapshot: {row['id']}"
                )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            packet = {
                "contract_version": 1,
                "story_id": row["id"],
                "content_hash": row["content_hash"],
                "language": row["language"],
                "crawl_timestamp": row["crawl_timestamp"],
                "crawl_month": row["crawl_month"],
                "source_url": row["source_url"],
                "source_file": row["source_file"],
                "quality_flags": json.loads(row["quality_flags_json"]),
                "accepted_filter_text": row["accepted_text"],
                "story_text": row["story_text"],
                "allowed_themes": [
                    {
                        "slug": theme["slug"],
                        "name": theme["name"],
                        "description": theme["description"],
                    }
                    for theme in themes
                ],
                "required_output": {
                    "eligible": "boolean",
                    "exclusion_reason": "string or null",
                    "summary": f"string in {config.primary_language}",
                    "primary_theme": "one allowed theme slug",
                    "secondary_themes": "zero or more allowed theme slugs",
                    "theme_fit": "number from 0 to 1",
                    "anchor_score": "number from 0 to 1",
                    "emotional_tone": "short string",
                    "digital_archaeology_angles": "array of grounded observations or questions",
                    "memorable_passages": "verbatim source excerpts only",
                    "sensitivity_notes": "array of concise notes",
                    "translation_needed": "boolean",
                    "pronunciation_items": "array of names, terms, or places",
                    "usage_recommendation": "anchor, featured, supporting, fragment, or contextual",
                },
            }
            handle.write(json.dumps(packet, ensure_ascii=False) + "\n")
    return len(rows)


def export_story_cards(
    config: ProjectConfig,
    output_path: Path,
    *,
    month: str | None = None,
) -> int:
    """Export current, non-duplicate story cards as portable JSONL."""
    conditions = [
        "s.is_present = 1",
        "s.duplicate_of IS NULL",
        "c.content_hash = s.content_hash",
    ]
    params: list[object] = []
    if month:
        conditions.append("s.crawl_month = ?")
        params.append(month)
    connection = connect(config.catalog_path)
    rows = connection.execute(
        f"""
        SELECT c.story_id, c.content_hash, c.analyzer, c.analyzer_version,
               c.card_json
          FROM story_cards AS c
          JOIN stories AS s ON s.id = c.story_id
         WHERE {' AND '.join(conditions)}
         ORDER BY s.crawl_timestamp, s.language, c.story_id,
                  c.analyzer, c.analyzer_version
        """,
        params,
    ).fetchall()
    connection.close()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            card = {
                "contract_version": 1,
                "story_id": row["story_id"],
                "content_hash": row["content_hash"],
                "analyzer": row["analyzer"],
                "analyzer_version": row["analyzer_version"],
                "analysis": json.loads(row["card_json"]),
            }
            handle.write(json.dumps(card, ensure_ascii=False) + "\n")
    return len(rows)


def import_story_cards(
    config: ProjectConfig,
    input_path: Path,
    *,
    analyzer: str | None = None,
    analyzer_version: str | None = None,
) -> tuple[int, int]:
    if (analyzer is None) != (analyzer_version is None):
        raise ValueError(
            "Provide both analyzer and analyzer_version, or neither when the "
            "JSONL embeds them"
        )
    allowed_themes = {theme["slug"] for theme in config.load_themes()["themes"]}
    cards = list(_read_jsonl(input_path))
    connection = connect(config.catalog_path)
    imported = skipped = 0
    try:
        connection.execute("BEGIN")
        for line_number, card in enumerate(cards, start=1):
            if not _store_story_card(
                connection,
                card,
                allowed_themes=allowed_themes,
                analyzer=analyzer
                or _required_string(card, "analyzer", line_number),
                analyzer_version=analyzer_version
                or _required_string(card, "analyzer_version", line_number),
                line_number=line_number,
            ):
                skipped += 1
                continue
            imported += 1
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return imported, skipped


def store_story_card(
    config: ProjectConfig,
    card: dict[str, Any],
    *,
    analyzer: str,
    analyzer_version: str,
) -> bool:
    """Validate and store one card. Return False when its source version is stale."""
    allowed_themes = {theme["slug"] for theme in config.load_themes()["themes"]}
    connection = connect(config.catalog_path)
    try:
        stored = _store_story_card(
            connection,
            card,
            allowed_themes=allowed_themes,
            analyzer=analyzer,
            analyzer_version=analyzer_version,
            line_number=1,
        )
        connection.commit()
        return stored
    finally:
        connection.close()


def _store_story_card(
    connection: Any,
    card: dict[str, Any],
    *,
    allowed_themes: set[str],
    analyzer: str,
    analyzer_version: str,
    line_number: int,
) -> bool:
    story_id = _required_string(card, "story_id", line_number)
    content_hash = _required_string(card, "content_hash", line_number)
    analysis = card.get("analysis", card.get("output"))
    if not isinstance(analysis, dict):
        raise ValueError(f"Line {line_number}: missing object field 'analysis'")
    current = connection.execute(
        "SELECT content_hash, story_text FROM stories WHERE id = ? AND is_present = 1",
        (story_id,),
    ).fetchone()
    if current is None or current["content_hash"] != content_hash:
        return False
    _validate_analysis(
        analysis, allowed_themes, line_number, source_text=current["story_text"]
    )
    connection.execute(
        """
        INSERT OR REPLACE INTO story_cards (
            story_id, content_hash, analyzer, analyzer_version, card_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            story_id,
            content_hash,
            analyzer,
            analyzer_version,
            json.dumps(analysis, ensure_ascii=False, sort_keys=True),
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ),
    )
    return True


def _read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open(encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Line {line_number}: expected a JSON object")
            yield value


def _required_string(card: dict[str, Any], key: str, line_number: int) -> str:
    value = card.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Line {line_number}: missing string field '{key}'")
    return value


def _validate_analysis(
    analysis: dict[str, Any],
    allowed_themes: set[str],
    line_number: int,
    *,
    source_text: str,
) -> None:
    if not isinstance(analysis.get("eligible"), bool):
        raise ValueError(f"Line {line_number}: analysis.eligible must be boolean")
    primary = analysis.get("primary_theme")
    if analysis["eligible"] and primary not in allowed_themes:
        raise ValueError(
            f"Line {line_number}: primary_theme must be one of {sorted(allowed_themes)}"
        )
    secondary = analysis.get("secondary_themes", [])
    if not isinstance(secondary, list) or any(value not in allowed_themes for value in secondary):
        raise ValueError(f"Line {line_number}: invalid secondary_themes")
    if not isinstance(analysis.get("summary"), str):
        raise ValueError(f"Line {line_number}: summary must be a string")
    if not isinstance(analysis.get("emotional_tone"), str):
        raise ValueError(f"Line {line_number}: emotional_tone must be a string")
    for score_name in ("theme_fit", "anchor_score"):
        value = analysis.get(score_name)
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or value < 0
            or value > 1
        ):
            raise ValueError(f"Line {line_number}: {score_name} must be from 0 to 1")
    for list_name in (
        "digital_archaeology_angles",
        "memorable_passages",
        "sensitivity_notes",
        "pronunciation_items",
    ):
        value = analysis.get(list_name)
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError(f"Line {line_number}: {list_name} must be an array of strings")
    if not isinstance(analysis.get("translation_needed"), bool):
        raise ValueError(f"Line {line_number}: translation_needed must be boolean")
    usage = analysis.get("usage_recommendation")
    allowed_usage = {"anchor", "featured", "supporting", "fragment", "contextual"}
    if usage not in allowed_usage:
        raise ValueError(f"Line {line_number}: invalid usage_recommendation")
    normalized_source = _normalize_text(source_text)
    for passage in analysis["memorable_passages"]:
        if passage and _normalize_text(passage) not in normalized_source:
            raise ValueError(
                f"Line {line_number}: memorable passage is not verbatim in story_text"
            )


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()
