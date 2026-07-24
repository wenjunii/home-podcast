from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Iterable

from .records import ParsedStory

STORY_HEADING = re.compile(r"(?m)^### (Source Story for Match(?:es)?[^\r\n]*)\r?$")
METADATA_LINE = re.compile(r"^- \*\*(.+?):\*\*\s*(.*)$")
LANGUAGE_LINE = re.compile(r"(?m)^\*\*Language:\*\*\s*`([^`]+)`")
CRAWL_TIMESTAMP = re.compile(r"CC-MAIN-(\d{14})")
MATCH_NUMBER = re.compile(r"\b(\d+)\b")
MARKDOWN_LINK = re.compile(r"^\[([^\]]+)\]\((.+)\)$")


def discover_story_files(exports_dir: Path) -> list[Path]:
    """Return story Markdown exports only; matches files and JSON exports are excluded."""
    return sorted(
        path
        for path in exports_dir.glob("stories_*.md")
        if path.is_file() and not path.name.lower().startswith("matches")
    )


def parse_story_file(path: Path) -> list[ParsedStory]:
    raw = path.read_text(encoding="utf-8-sig")
    language_match = LANGUAGE_LINE.search(raw)
    language = (
        language_match.group(1).strip()
        if language_match
        else path.stem.removeprefix("stories_")
    )
    headings = list(STORY_HEADING.finditer(raw))
    stories: list[ParsedStory] = []
    for ordinal, heading_match in enumerate(headings, start=1):
        end = headings[ordinal].start() if ordinal < len(headings) else len(raw)
        block = raw[heading_match.end() : end]
        stories.append(
            _parse_story_block(
                heading=heading_match.group(1).strip(),
                block=block,
                language=language,
                path=path,
                ordinal=ordinal,
            )
        )
    return stories


def parse_story_files(paths: Iterable[Path]) -> Iterable[ParsedStory]:
    for path in paths:
        yield from parse_story_file(path)


def _parse_story_block(
    *, heading: str, block: str, language: str, path: Path, ordinal: int
) -> ParsedStory:
    accepted_start = block.find("#### Accepted Filter Paragraph")
    extracted_start = block.find("#### Extracted Source Story")
    metadata_region = block if accepted_start < 0 else block[:accepted_start]
    metadata: dict[str, str] = {}
    for line in metadata_region.splitlines():
        match = METADATA_LINE.match(line.strip())
        if match:
            metadata[match.group(1).strip()] = match.group(2).strip()

    accepted_text = _extract_section(
        block, "#### Accepted Filter Paragraph", "#### Extracted Source Story"
    )
    story_text = _extract_section(block, "#### Extracted Source Story", None)
    source_url = _plain_metadata_value(metadata.get("Source URL", ""))
    source_file = _plain_metadata_value(metadata.get("Source File", ""))
    crawl_dataset = _plain_metadata_value(metadata.get("Crawl Dataset", ""))
    crawl_timestamp = _extract_crawl_timestamp(source_file)
    crawl_month = f"{crawl_timestamp[:4]}-{crawl_timestamp[5:7]}" if crawl_timestamp else ""
    match_references = tuple(int(value) for value in MATCH_NUMBER.findall(heading))
    content_hash = _hash_text(_normalized_for_hash(story_text))
    # A few captured pages contain multiple independently extracted stories. The
    # smallest match reference distinguishes those records while remaining stable
    # when later extraction appends additional matches to an existing story.
    match_discriminator = str(min(match_references)) if match_references else ""
    identity_basis = "\0".join(
        [language, source_url, source_file, match_discriminator]
    )
    if not source_url and not source_file:
        identity_basis = f"{language}\0{content_hash}"
    story_id = f"story-{_hash_text(identity_basis)[:24]}"
    quality_flags = tuple(_quality_flags(story_text, block))
    record_payload = {
        "accepted_text": accepted_text,
        "story_text": story_text,
        "metadata": metadata,
        "quality_flags": quality_flags,
    }
    record_hash = _hash_text(
        json.dumps(record_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    return ParsedStory(
        story_id=story_id,
        language=language,
        heading=heading,
        source_markdown=path.resolve(),
        source_ordinal=ordinal,
        source_url=source_url,
        source_file=source_file,
        crawl_dataset=crawl_dataset,
        crawl_timestamp=crawl_timestamp,
        crawl_month=crawl_month,
        match_references=match_references,
        accepted_text=accepted_text,
        story_text=story_text,
        metadata=metadata,
        quality_flags=quality_flags,
        content_hash=content_hash,
        record_hash=record_hash,
    )


def _extract_section(block: str, heading: str, next_heading: str | None) -> str:
    start = block.find(heading)
    if start < 0:
        return ""
    start += len(heading)
    end = block.find(next_heading, start) if next_heading else len(block)
    if end < 0:
        end = len(block)
    section = block[start:end]
    section = re.split(r"(?m)^---\s*$", section, maxsplit=1)[0]
    lines: list[str] = []
    for line in section.strip().splitlines():
        if line.startswith("> "):
            lines.append(line[2:])
        elif line == ">":
            lines.append("")
        else:
            lines.append(line)
    return "\n".join(lines).strip()


def _plain_metadata_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
        return value[1:-1]
    match = MARKDOWN_LINK.match(value)
    if match:
        return match.group(2)
    return value


def _extract_crawl_timestamp(source_file: str) -> str:
    matches = CRAWL_TIMESTAMP.findall(source_file)
    if not matches:
        return ""
    value = matches[-1]
    return (
        f"{value[0:4]}-{value[4:6]}-{value[6:8]}"
        f"T{value[8:10]}:{value[10:12]}:{value[12:14]}Z"
    )


def _normalized_for_hash(value: str) -> str:
    return "\n".join(
        line.rstrip() for line in unicodedata.normalize("NFC", value).strip().splitlines()
    )


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _quality_flags(story_text: str, raw_block: str) -> list[str]:
    flags: list[str] = []
    lowered = story_text.casefold()
    if not story_text.strip():
        flags.append("missing_story_text")
    if len(story_text.split()) < 40:
        flags.append("very_short")
    if len(story_text.split()) > 6000:
        flags.append("very_long")
    if "intervening source paragraphs omitted" in raw_block:
        flags.append("source_has_omissions")
    mojibake_markers = ("Ã©", "Ã£", "â€™", "â€œ", "â€", "Â ")
    if any(marker in story_text for marker in mojibake_markers):
        flags.append("possible_mojibake")
    boilerplate_terms = (
        "leave a reply",
        "privacy policy",
        "terms of use",
        "previous post",
        "next post",
        "rss",
        "archive",
        "login",
        "copyright",
    )
    if sum(term in lowered for term in boilerplate_terms) >= 4:
        flags.append("likely_page_boilerplate")
    if not _extract_crawl_timestamp(_plain_metadata_value(_metadata_from_block(raw_block, "Source File"))):
        flags.append("missing_crawl_timestamp")
    return flags


def _metadata_from_block(block: str, label: str) -> str:
    for line in block.splitlines():
        match = METADATA_LINE.match(line.strip())
        if match and match.group(1).strip() == label:
            return match.group(2).strip()
    return ""
