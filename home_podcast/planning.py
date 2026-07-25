from __future__ import annotations

import json
import hashlib
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import ProjectConfig
from .database import connect


def create_month_proposal(
    config: ProjectConfig,
    month: str,
    output_path: Path,
    cohort_path: Path | None = None,
) -> dict[str, Any]:
    theme_config = config.load_themes()["themes"]
    theme_by_slug = {theme["slug"]: theme for theme in theme_config}
    cohort: dict[str, Any] | None = None
    expected_cohort: dict[str, str] | None = None
    if cohort_path is not None:
        cohort = json.loads(cohort_path.read_text(encoding="utf-8"))
        if cohort.get("kind") != "crawl_month_cohort":
            raise ValueError(f"Not a crawl-month cohort manifest: {cohort_path}")
        if cohort.get("crawl_month") != month:
            raise ValueError(
                f"Cohort month {cohort.get('crawl_month')} does not match {month}"
            )
        expected_cohort = {
            item["story_id"]: item["content_hash"] for item in cohort["stories"]
        }
        if len(expected_cohort) != len(cohort["stories"]):
            raise ValueError(f"Cohort contains duplicate story IDs: {cohort_path}")

    connection = connect(config.catalog_path)
    rows = connection.execute(
        """
        SELECT s.*,
               (
                   SELECT c.card_json
                     FROM story_cards AS c
                    WHERE c.story_id = s.id
                      AND c.content_hash = s.content_hash
                    ORDER BY c.created_at DESC
                    LIMIT 1
               ) AS card_json
          FROM stories AS s
         WHERE s.is_present = 1
           AND s.duplicate_of IS NULL
           AND s.crawl_month = ?
         ORDER BY s.crawl_timestamp, s.language, s.id
        """,
        (month,),
    ).fetchall()
    connection.close()
    if expected_cohort is not None:
        rows_by_id = {row["id"]: row for row in rows}
        missing_or_changed = [
            story_id
            for story_id, content_hash in expected_cohort.items()
            if story_id not in rows_by_id
            or rows_by_id[story_id]["content_hash"] != content_hash
        ]
        if missing_or_changed:
            preview = ", ".join(missing_or_changed[:5])
            raise ValueError(
                "Frozen cohort stories changed or disappeared; "
                f"first affected IDs: {preview}"
            )
        rows = [row for row in rows if row["id"] in expected_cohort]
    if not rows:
        raise ValueError(f"No present, unique stories found for crawl month {month}")

    grouped: dict[str, list[dict[str, Any]]] = {}
    unanalyzed: list[str] = []
    ineligible: list[dict[str, str]] = []
    for row in rows:
        if not row["card_json"]:
            unanalyzed.append(row["id"])
            continue
        card = json.loads(row["card_json"])
        if not card.get("eligible", False):
            ineligible.append(
                {
                    "story_id": row["id"],
                    "reason": str(card.get("exclusion_reason") or "Not eligible"),
                }
            )
            continue
        slug = card["primary_theme"]
        grouped.setdefault(slug, []).append(
            {
                "story_id": row["id"],
                "content_hash": row["content_hash"],
                "language": row["language"],
                "crawl_timestamp": row["crawl_timestamp"],
                "source_url": row["source_url"],
                "usage_type": card.get("usage_recommendation", "supporting"),
                "anchor_score": float(card.get("anchor_score", 0)),
                "theme_fit": float(card.get("theme_fit", 0)),
                "summary": str(card.get("summary", "")),
                "secondary_themes": card.get("secondary_themes", []),
            }
        )

    installments: list[dict[str, Any]] = []
    sequence = 0
    for theme in theme_config:
        stories = grouped.get(theme["slug"], [])
        if not stories:
            continue
        stories.sort(
            key=lambda item: (
                -item["anchor_score"],
                -item["theme_fit"],
                item["crawl_timestamp"],
                item["story_id"],
            )
        )
        part_count = math.ceil(len(stories) / config.target_stories_per_installment)
        for part_index in range(part_count):
            sequence += 1
            start = part_index * config.target_stories_per_installment
            chunk = stories[start : start + config.target_stories_per_installment]
            title = theme["name"]
            if part_count > 1:
                title += f", Part {part_index + 1}"
            installments.append(
                {
                    "episode_id": f"{month}.{sequence:02d}",
                    "archive_volume": month,
                    "sequence": sequence,
                    "title": title,
                    "theme_slug": theme["slug"],
                    "theme_name": theme["name"],
                    "theme_description": theme["description"],
                    "archaeology_question": theme["archaeology_questions"][
                        part_index % len(theme["archaeology_questions"])
                    ],
                    "status": "proposed",
                    "story_count": len(chunk),
                    "stories": chunk,
                }
            )

    proposal = {
        "contract_version": 1,
        "project": config.project_name,
        "archive_volume": month,
        "meaning_of_archive_volume": (
            "The calendar month when Common Crawl captured the source page; "
            "not necessarily the story publication month."
        ),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cohort": (
            {
                "path": str(cohort_path),
                "label": cohort.get("label"),
                "story_count": cohort.get("story_count"),
            }
            if cohort is not None
            else None
        ),
        "policy": {
            "coverage": "maximum_responsible_coverage",
            "target_stories_per_installment": config.target_stories_per_installment,
            "published_episodes_are_immutable": True,
            "late_arrivals": "supplement_or_later_cross_month_episode",
        },
        "installments": installments,
        "coverage": {
            "unique_present_stories": len(rows),
            "assigned_eligible_stories": sum(item["story_count"] for item in installments),
            "unanalyzed_story_ids": unanalyzed,
            "ineligible_stories": ineligible,
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(proposal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return proposal


def snapshot_crawl_month(
    config: ProjectConfig,
    month: str,
    label: str,
    output_path: Path,
    *,
    analyzed_only: bool = False,
) -> tuple[dict[str, Any], bool]:
    connection = connect(config.catalog_path)
    analysis_condition = (
        """
           AND EXISTS (
               SELECT 1
                 FROM story_cards AS c
                WHERE c.story_id = stories.id
                  AND c.content_hash = stories.content_hash
           )
        """
        if analyzed_only
        else ""
    )
    rows = connection.execute(
        f"""
        SELECT id, content_hash, language, crawl_dataset, crawl_timestamp
          FROM stories
         WHERE is_present = 1
           AND duplicate_of IS NULL
           AND crawl_month = ?
           {analysis_condition}
         ORDER BY crawl_timestamp, language, id
        """,
        (month,),
    ).fetchall()
    connection.close()
    if not rows:
        raise ValueError(f"No present, unique stories found for crawl month {month}")
    snapshot = {
        "contract_version": 1,
        "kind": "crawl_month_cohort",
        "label": label,
        "crawl_month": month,
        "story_count": len(rows),
        "snapshot_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "selection_policy": (
            "present unique stories with a current story card"
            if analyzed_only
            else "all present unique stories"
        ),
        "capture_time_basis": (
            "Timestamp embedded in Source File. For this December 2013 cohort it "
            "matches the upstream WARC capture month."
        ),
        "stories": [
            {
                "story_id": row["id"],
                "content_hash": row["content_hash"],
                "language": row["language"],
                "crawl_dataset": row["crawl_dataset"],
                "crawl_timestamp": row["crawl_timestamp"],
            }
            for row in rows
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        existing = json.loads(output_path.read_text(encoding="utf-8"))
        same = (
            existing.get("crawl_month") == month
            and existing.get("stories") == snapshot["stories"]
        )
        if same:
            return existing, False
        raise ValueError(
            f"Refusing to overwrite a different frozen cohort: {output_path}"
        )
    output_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return snapshot, True


def prepare_script_packet(
    config: ProjectConfig,
    planning_source_path: Path,
    episode_id: str,
    output_path: Path,
) -> dict[str, Any]:
    planning_source = json.loads(planning_source_path.read_text(encoding="utf-8"))
    if "installments" in planning_source:
        installment = next(
            (
                item
                for item in planning_source["installments"]
                if item["episode_id"] == episode_id
            ),
            None,
        )
    elif planning_source.get("manifest_status") == "locked":
        installment = {
            **planning_source["episode"],
            "stories": planning_source["stories"],
        }
        if installment.get("episode_id") != episode_id:
            installment = None
    else:
        installment = None
    if installment is None:
        raise ValueError(f"Episode {episode_id} is not present in {planning_source_path}")
    story_ids = [item["story_id"] for item in installment["stories"]]
    connection = connect(config.catalog_path)
    placeholders = ",".join("?" for _ in story_ids)
    rows = connection.execute(
        f"SELECT * FROM stories WHERE id IN ({placeholders})", story_ids
    ).fetchall()
    connection.close()
    row_by_id = {row["id"]: row for row in rows}
    evidence = []
    for assignment in installment["stories"]:
        row = row_by_id.get(assignment["story_id"])
        if row is None or row["content_hash"] != assignment["content_hash"]:
            raise ValueError(
                f"Story changed or disappeared after proposal: {assignment['story_id']}"
            )
        evidence.append(
            {
                **assignment,
                "source_file": row["source_file"],
                "source_markdown": row["source_markdown"],
                "accepted_filter_text": row["accepted_text"],
                "story_text": row["story_text"],
                "quality_flags": json.loads(row["quality_flags_json"]),
            }
        )
    packet = {
        "contract_version": 1,
        "episode": {key: value for key, value in installment.items() if key != "stories"},
        "show_bible": config.load_show_bible(),
        "evidence": evidence,
        "writing_requirements": {
            "use_every_evidence_story": True,
            "allowed_usage_types": [
                "anchor",
                "featured",
                "supporting",
                "fragment",
                "contextual",
            ],
            "source_ids_required_per_grounded_segment": True,
            "exact_quotes_must_be_verbatim": True,
            "invented_author_dialogue_forbidden": True,
            "synthetic_host_disclosure_required": True,
            "output_contract": "contracts/script.schema.json",
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return packet


def lock_episode_manifest(
    config: ProjectConfig,
    proposal_path: Path,
    episode_id: str,
) -> tuple[Path, bool]:
    proposal_bytes = proposal_path.read_bytes()
    proposal = json.loads(proposal_bytes)
    installment = next(
        (item for item in proposal["installments"] if item["episode_id"] == episode_id),
        None,
    )
    if installment is None:
        raise ValueError(f"Episode {episode_id} is not present in {proposal_path}")
    if not installment.get("stories"):
        raise ValueError(f"Episode {episode_id} has no assigned stories")

    connection = connect(config.catalog_path)
    for assignment in installment["stories"]:
        row = connection.execute(
            "SELECT content_hash, is_present FROM stories WHERE id = ?",
            (assignment["story_id"],),
        ).fetchone()
        if (
            row is None
            or not row["is_present"]
            or row["content_hash"] != assignment["content_hash"]
        ):
            connection.close()
            raise ValueError(
                f"Cannot lock: story changed or disappeared: {assignment['story_id']}"
            )
    connection.close()

    manifest = {
        "contract_version": 1,
        "manifest_status": "locked",
        "locked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "proposal_sha256": hashlib.sha256(proposal_bytes).hexdigest(),
        "episode": {key: value for key, value in installment.items() if key != "stories"},
        "stories": installment["stories"],
        "immutability": (
            "Do not rewrite after publication. Late discoveries belong in a supplement "
            "or later cross-month episode."
        ),
    }
    episode_dir = config.episodes_dir / episode_id
    episode_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = episode_dir / "manifest.json"
    serialized = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        same_episode = (
            existing.get("episode") == manifest["episode"]
            and existing.get("stories") == manifest["stories"]
        )
        if same_episode:
            return manifest_path, False
        raise ValueError(
            f"Refusing to overwrite locked manifest with different content: {manifest_path}"
        )
    with manifest_path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(serialized)
    return manifest_path, True
