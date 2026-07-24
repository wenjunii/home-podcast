from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from home_podcast.ingest import ingest_exports


def fixture(story_text: str, extra: str = "") -> str:
    return f"""# Expanded Home and Belonging Stories

**Language:** `en`

### Source Story for Match 1
- **Source URL:** [https://example.test/a](https://example.test/a)
- **Crawl Dataset:** `CC-MAIN-2013-20`
- **Source File:** `crawl-data/CC-MAIN-2013-20/wet/CC-MAIN-20130516094552-00001.warc.wet.gz`

#### Accepted Filter Paragraph

> Home.

#### Extracted Source Story

> {story_text}

---
{extra}
"""


SECOND = """
### Source Story for Match 2
- **Source URL:** [https://example.test/b](https://example.test/b)
- **Crawl Dataset:** `CC-MAIN-2013-20`
- **Source File:** `crawl-data/CC-MAIN-2013-20/wet/CC-MAIN-20130516094553-00002.warc.wet.gz`

#### Accepted Filter Paragraph

> Belonging.

#### Extracted Source Story

> A second story about belonging and community.

---
"""


class IncrementalIngestTests(unittest.TestCase):
    def test_unchanged_updated_and_new_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exports = root / "exports"
            exports.mkdir()
            catalog = root / "catalog.sqlite3"
            source = exports / "stories_en.md"
            source.write_text(fixture("A first story about home."), encoding="utf-8")

            first = ingest_exports(catalog, exports)
            self.assertEqual(first.inserted, 1)
            second = ingest_exports(catalog, exports)
            self.assertEqual(second.unchanged, 1)

            source.write_text(
                fixture("A revised first story about home.", SECOND), encoding="utf-8"
            )
            third = ingest_exports(catalog, exports)
            self.assertEqual(third.updated, 1)
            self.assertEqual(third.inserted, 1)

            connection = sqlite3.connect(catalog)
            story_count = connection.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
            version_count = connection.execute(
                "SELECT COUNT(*) FROM story_versions"
            ).fetchone()[0]
            connection.close()
            self.assertEqual(story_count, 2)
            self.assertEqual(version_count, 3)


if __name__ == "__main__":
    unittest.main()
