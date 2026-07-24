from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ParsedStory:
    story_id: str
    language: str
    heading: str
    source_markdown: Path
    source_ordinal: int
    source_url: str
    source_file: str
    crawl_dataset: str
    crawl_timestamp: str
    crawl_month: str
    match_references: tuple[int, ...]
    accepted_text: str
    story_text: str
    metadata: dict[str, str]
    quality_flags: tuple[str, ...]
    content_hash: str
    record_hash: str


@dataclass(frozen=True)
class IngestStats:
    run_id: int
    files_scanned: int
    stories_seen: int
    inserted: int
    updated: int
    unchanged: int
    reappeared: int
    missing: int


@dataclass(frozen=True)
class StoryCard:
    story_id: str
    content_hash: str
    analyzer: str
    analyzer_version: str
    analysis: dict[str, Any]
