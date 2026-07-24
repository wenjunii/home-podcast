from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from home_podcast.parser import discover_story_files, parse_story_file


FIXTURE = """# Expanded Home and Belonging Stories

**Language:** `es`
**Unique Stories:** 1

---

### Source Story for Matches 1, 2
- **Source URL:** [https://example.test/story](https://example.test/story)
- **Crawl Dataset:** `CC-MAIN-2013-48`
- **Source File:** `crawl-data/CC-MAIN-2013-48/segments/1/wet/CC-MAIN-20131204133352-00001.warc.wet.gz`

#### Accepted Filter Paragraph

> Mi hogar.

#### Extracted Source Story

> Mi hogar está aquí.
>
> También vive en mi memoria.

---
"""


class ParserTests(unittest.TestCase):
    def test_parses_timestamp_language_and_sections(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stories_es.md"
            path.write_text(FIXTURE, encoding="utf-8")
            story = parse_story_file(path)[0]
            self.assertEqual(story.language, "es")
            self.assertEqual(story.crawl_timestamp, "2013-12-04T13:33:52Z")
            self.assertEqual(story.crawl_month, "2013-12")
            self.assertEqual(story.match_references, (1, 2))
            self.assertIn("También", story.story_text)

    def test_story_id_does_not_change_when_match_numbers_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stories_es.md"
            path.write_text(FIXTURE, encoding="utf-8")
            first = parse_story_file(path)[0]
            path.write_text(
                FIXTURE.replace("Matches 1, 2", "Matches 1, 2, 9"), encoding="utf-8"
            )
            second = parse_story_file(path)[0]
            self.assertEqual(first.story_id, second.story_id)

    def test_discovery_excludes_matches_and_non_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "stories_en.md").write_text(FIXTURE, encoding="utf-8")
            (root / "matches_en.md").write_text("ignored", encoding="utf-8")
            (root / "stories.jsonl.gz").write_bytes(b"ignored")
            self.assertEqual(
                [path.name for path in discover_story_files(root)], ["stories_en.md"]
            )


if __name__ == "__main__":
    unittest.main()
