from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ingest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_root TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    files_scanned INTEGER NOT NULL DEFAULT 0,
    stories_seen INTEGER NOT NULL DEFAULT 0,
    inserted INTEGER NOT NULL DEFAULT 0,
    updated INTEGER NOT NULL DEFAULT 0,
    unchanged INTEGER NOT NULL DEFAULT 0,
    reappeared INTEGER NOT NULL DEFAULT 0,
    missing INTEGER NOT NULL DEFAULT 0,
    error TEXT
);

CREATE TABLE IF NOT EXISTS stories (
    id TEXT PRIMARY KEY,
    language TEXT NOT NULL,
    heading TEXT NOT NULL,
    source_root TEXT NOT NULL,
    source_markdown TEXT NOT NULL,
    source_ordinal INTEGER NOT NULL,
    source_url TEXT NOT NULL,
    source_file TEXT NOT NULL,
    crawl_dataset TEXT NOT NULL,
    crawl_timestamp TEXT NOT NULL,
    crawl_month TEXT NOT NULL,
    match_references_json TEXT NOT NULL,
    accepted_text TEXT NOT NULL,
    story_text TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    quality_flags_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    record_hash TEXT NOT NULL,
    duplicate_of TEXT REFERENCES stories(id),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    last_seen_run_id INTEGER NOT NULL REFERENCES ingest_runs(id),
    is_present INTEGER NOT NULL DEFAULT 1 CHECK (is_present IN (0, 1))
);

CREATE INDEX IF NOT EXISTS idx_stories_month ON stories(crawl_month);
CREATE INDEX IF NOT EXISTS idx_stories_language ON stories(language);
CREATE INDEX IF NOT EXISTS idx_stories_content_hash ON stories(content_hash);
CREATE INDEX IF NOT EXISTS idx_stories_presence ON stories(is_present);

CREATE TABLE IF NOT EXISTS story_versions (
    story_id TEXT NOT NULL REFERENCES stories(id),
    record_hash TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    seen_at TEXT NOT NULL,
    accepted_text TEXT NOT NULL,
    story_text TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    quality_flags_json TEXT NOT NULL,
    PRIMARY KEY (story_id, record_hash)
);

CREATE TABLE IF NOT EXISTS story_cards (
    story_id TEXT NOT NULL REFERENCES stories(id),
    content_hash TEXT NOT NULL,
    analyzer TEXT NOT NULL,
    analyzer_version TEXT NOT NULL,
    card_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (story_id, content_hash, analyzer, analyzer_version)
);

CREATE INDEX IF NOT EXISTS idx_story_cards_current
ON story_cards(story_id, content_hash);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.executescript(SCHEMA)
    connection.execute(
        "INSERT OR REPLACE INTO schema_meta(key, value) VALUES ('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    connection.commit()
    return connection
