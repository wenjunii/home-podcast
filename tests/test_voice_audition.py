from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from home_podcast.voice_audition import prepare_voice_candidate_audition_jobs


class VoiceCandidateAuditionTests(unittest.TestCase):
    def test_prepares_same_text_for_screened_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audition_path = root / "audition.json"
            candidates_path = root / "candidates.json"
            jobs_path = root / "work" / "jobs.jsonl"
            audition_path.write_text(
                json.dumps(
                    {
                        "contract_version": 1,
                        "audition_id": "accent-test",
                        "text": "A page survives.",
                        "delivery": {"tone": "warm"},
                        "pronunciation": {},
                    }
                ),
                encoding="utf-8",
            )
            candidates_path.write_text(
                json.dumps(
                    {
                        "contract_version": 1,
                        "provider": "elevenlabs",
                        "screening_policy": {
                            "minimum_notice_period_days": 365,
                            "maximum_credit_rate": 1,
                        },
                        "candidates": [
                            _candidate("irish-a", "voice-a", "irish", "en-IE"),
                            _candidate("indian-b", "voice-b", "indian", "en-IN"),
                        ],
                    }
                ),
                encoding="utf-8",
            )
            report = prepare_voice_candidate_audition_jobs(
                _config(root),
                audition_path,
                candidates_path,
                jobs_path,
            )
            jobs = [
                json.loads(line)
                for line in jobs_path.read_text(encoding="utf-8").splitlines()
            ]

            self.assertEqual(report["candidates"], 2)
            self.assertEqual(report["output_format"], "mp3_44100_192")
            self.assertEqual(len({job["render_text"] for job in jobs}), 1)
            self.assertEqual({job["accent"] for job in jobs}, {"irish", "indian"})
            self.assertTrue(
                all("mp3_44100_192" in job["preview_mp3"] for job in jobs)
            )

    def test_rejects_unverified_or_short_notice_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audition_path = root / "audition.json"
            candidates_path = root / "candidates.json"
            audition_path.write_text(
                json.dumps(
                    {
                        "contract_version": 1,
                        "audition_id": "accent-test",
                        "text": "A page survives.",
                    }
                ),
                encoding="utf-8",
            )
            candidate = _candidate("candidate", "voice-a", "irish", "en-IE")
            candidate["notice_period_days"] = 30
            candidates_path.write_text(
                json.dumps(
                    {
                        "contract_version": 1,
                        "provider": "elevenlabs",
                        "screening_policy": {
                            "minimum_notice_period_days": 365,
                            "maximum_credit_rate": 1,
                        },
                        "candidates": [candidate],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "notice days"):
                prepare_voice_candidate_audition_jobs(
                    _config(root),
                    audition_path,
                    candidates_path,
                    root / "jobs.jsonl",
                )


def _candidate(
    candidate_id: str,
    voice_id: str,
    accent: str,
    locale: str,
) -> dict:
    return {
        "candidate_id": candidate_id,
        "display_name": candidate_id,
        "voice_name": candidate_id,
        "voice_id": voice_id,
        "accent": accent,
        "locale": locale,
        "english_verified": True,
        "notice_period_days": 730,
        "credit_rate": 1,
        "proposed_roles": ["curious_guide"],
    }


def _config(root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        audio_dir=root / "audio",
        work_dir=root / "work",
        speech_provider={
            "type": "elevenlabs_tts",
            "model": "eleven_v3",
            "output_format": "mp3_44100_192",
            "language_code": "en",
            "voice_settings": {"stability": 0.5},
        },
    )


if __name__ == "__main__":
    unittest.main()
