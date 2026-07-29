from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from scripts.sync_story_exports import sync_story_exports


def story_block(match: int, timestamp: str, text: str, capture_count: int = 1) -> str:
    return f"""
### Source Story for Match {match}

- **Source URL:** `https://example.com/{match}`
- **Source File:** `crawl-data/CC-MAIN-2013-48/wet/CC-MAIN-{timestamp}-00001.warc.wet.gz`
- **Crawl Dataset:** `CC-MAIN-2013-48`
- **Capture Count:** {capture_count}

#### Accepted Filter Paragraph

> A paragraph about home and belonging with enough context for the parser.

#### Extracted Source Story

> {text}
"""


def export_file(*blocks: str) -> str:
    return "# Stories\n\n**Language:** `en`\n\n" + "\n---\n".join(blocks)


class SyncStoryExportsTests(unittest.TestCase):
    def test_dry_run_then_apply_copies_only_story_exports(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            destination.mkdir()
            old_text = " ".join(["home"] * 80)
            new_text = " ".join(["belonging"] * 80)
            (destination / "stories_en.md").write_text(
                export_file(story_block(1, "20131204133352", old_text)),
                encoding="utf-8",
            )
            (source / "stories_en.md").write_text(
                export_file(
                    story_block(1, "20131204133352", old_text, capture_count=2),
                    story_block(2, "20131204133353", new_text),
                ),
                encoding="utf-8",
            )
            (source / "matches_en.md").write_text("not a story export", encoding="utf-8")

            dry_run = sync_story_exports(source, destination)
            self.assertFalse(dry_run["applied"])
            self.assertEqual(dry_run["source_stories"], 2)
            self.assertEqual(dry_run["destination_stories_before"], 1)
            self.assertEqual(dry_run["new_story_ids"], 1)
            self.assertEqual(dry_run["shared_content_changed"], 0)
            self.assertEqual(dry_run["shared_record_changed"], 1)

            applied = sync_story_exports(source, destination, apply=True)
            self.assertTrue(applied["applied"])
            self.assertEqual(applied["destination_stories_after"], 2)
            self.assertEqual(applied["copied_files"], ["stories_en.md"])
            self.assertFalse((destination / "matches_en.md").exists())

    def test_stale_story_file_requires_explicit_prune(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            destination = root / "destination"
            source.mkdir()
            destination.mkdir()
            text = " ".join(["home"] * 80)
            (source / "stories_en.md").write_text(
                export_file(story_block(1, "20131204133352", text)),
                encoding="utf-8",
            )
            (destination / "stories_en.md").write_text(
                export_file(story_block(1, "20131204133352", text)),
                encoding="utf-8",
            )
            (destination / "stories_fr.md").write_text(
                "# Stories\n\n**Language:** `fr`\n\n"
                + story_block(3, "20131204133354", text),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "stale"):
                sync_story_exports(source, destination, apply=True)

            applied = sync_story_exports(source, destination, apply=True, prune=True)
            self.assertEqual(applied["pruned_files"], ["stories_fr.md"])
            self.assertFalse((destination / "stories_fr.md").exists())


if __name__ == "__main__":
    unittest.main()
