from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from home_podcast.casting import create_episode_cast


class CastingTests(unittest.TestCase):
    def test_episode_cast_is_rotating_reproducible_and_frozen(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            roster_path = root / "roster.json"
            roster_path.write_text(json.dumps(_roster()), encoding="utf-8")
            first_path = root / "first.json"
            first, created = create_episode_cast(
                roster_path,
                "2013-12.01",
                first_path,
            )
            repeated, created_again = create_episode_cast(
                roster_path,
                "2013-12.01",
                first_path,
            )
            self.assertTrue(created)
            self.assertFalse(created_again)
            self.assertEqual(first, repeated)
            self.assertEqual(
                len({host["accent"] for host in first["hosts"]}),
                3,
            )
            self.assertEqual(
                len({host["person_id"] for host in first["hosts"]}),
                3,
            )

            lineups = set()
            accent_assignments = set()
            for sequence in range(1, 8):
                episode_id = f"2014-01.{sequence:02d}"
                episode_cast, _ = create_episode_cast(
                    roster_path,
                    episode_id,
                    root / f"{episode_id}.json",
                )
                lineups.add(
                    tuple(host["person_id"] for host in episode_cast["hosts"])
                )
                accent_assignments.add(
                    tuple(host["accent"] for host in episode_cast["hosts"])
                )
                self.assertEqual(
                    len({host["accent"] for host in episode_cast["hosts"]}),
                    3,
                )
            self.assertGreater(len(lineups), 1)
            self.assertGreater(len(accent_assignments), 1)


def _roster() -> dict:
    return {
        "contract_version": 1,
        "provider": "test",
        "roles": [
            {
                "id": role,
                "candidates": [
                    {
                        "person_id": f"person-{index}",
                        "display_name": f"Person {index}",
                        "voice_name": f"Voice {index}",
                        "voice_id": f"voice-{index}",
                        "accent": ("american", "british", "australian")[index],
                    }
                    for index in range(3)
                ],
            }
            for role in ("curious_guide", "archive_nerd", "connector")
        ],
    }


if __name__ == "__main__":
    unittest.main()
