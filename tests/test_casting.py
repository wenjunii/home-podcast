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

            lineups = set()
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
            self.assertGreater(len(lineups), 1)


def _roster() -> dict:
    return {
        "contract_version": 1,
        "provider": "test",
        "roles": [
            {
                "id": role,
                "candidates": [
                    {
                        "person_id": f"{role}-{index}",
                        "display_name": f"{role}-{index}",
                        "voice_name": f"Voice {role}-{index}",
                        "voice_id": f"voice-{role}-{index}",
                    }
                    for index in range(3)
                ],
            }
            for role in ("curious_guide", "archive_nerd", "connector")
        ],
    }


if __name__ == "__main__":
    unittest.main()
