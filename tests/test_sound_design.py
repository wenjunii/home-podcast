from __future__ import annotations

import json
import tempfile
import unittest
import wave
from pathlib import Path

from home_podcast.sound_design import (
    prepare_sfx_jobs,
    resolve_sound_cues,
    resolve_soundscape,
    validate_sound_design,
)


class SoundDesignTests(unittest.TestCase):
    def test_validates_and_prepares_only_generated_cues(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script_path = root / "script.json"
            cue_path = root / "sound-design.json"
            script_path.write_text(
                json.dumps(
                    {
                        "episode_id": "2013-12.01",
                        "segments": [{"segment_id": "s1"}],
                    }
                ),
                encoding="utf-8",
            )
            cue_path.write_text(
                json.dumps(_sound_design()),
                encoding="utf-8",
            )

            report = validate_sound_design(cue_path, script_path)
            self.assertTrue(report["valid"], report["errors"])
            jobs_path = root / "jobs.jsonl"
            count = prepare_sfx_jobs(
                cue_path,
                script_path,
                jobs_path,
                root / "cache",
                provider="example",
                model="effects-v1",
            )
            self.assertEqual(count, 1)
            job = json.loads(jobs_path.read_text(encoding="utf-8"))
            self.assertEqual(job["cue_id"], "generated-cue")
            self.assertEqual(job["generation_duration_ms"], 1000)
            self.assertNotIn("licensed-cue", jobs_path.read_text(encoding="utf-8"))

    def test_rejects_unknown_anchor_and_implicit_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            script_path = root / "script.json"
            cue_path = root / "sound-design.json"
            script_path.write_text(
                json.dumps(
                    {
                        "episode_id": "2013-12.01",
                        "segments": [{"segment_id": "s1"}],
                    }
                ),
                encoding="utf-8",
            )
            sound_design = _sound_design()
            sound_design["cues"][0]["anchor"]["segment_id"] = "missing"
            sound_design["cues"][0]["provenance"]["presentation"] = "archival"
            cue_path.write_text(json.dumps(sound_design), encoding="utf-8")

            report = validate_sound_design(cue_path, script_path)
            self.assertFalse(report["valid"])
            self.assertTrue(
                any("unknown segment" in error for error in report["errors"])
            )
            self.assertTrue(
                any("illustrative sound design" in error for error in report["errors"])
            )

    def test_resolves_generated_and_licensed_assets_to_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cue_path = root / "sound-design.json"
            sound_design = _sound_design()
            licensed_path = root / "licensed.wav"
            generated_path = root / "generated.wav"
            _write_silence(licensed_path)
            _write_silence(generated_path)
            sound_design["cues"][1]["source"]["path"] = "licensed.wav"
            cue_path.write_text(json.dumps(sound_design), encoding="utf-8")
            jobs_path = root / "jobs.jsonl"
            jobs_path.write_text(
                json.dumps(
                    {
                        "cue_id": "generated-cue",
                        "output_audio": str(generated_path),
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            cues = resolve_sound_cues(
                cue_path,
                [
                    {
                        "segment_id": "s1",
                        "start_ms": 2000,
                        "end_ms": 3000,
                    }
                ],
                jobs_path,
            )
            self.assertEqual(cues[0]["start_ms"], 2000)
            self.assertEqual(cues[1]["start_ms"], 2500)
            self.assertEqual(Path(cues[0]["asset_audio"]), generated_path)
            self.assertEqual(Path(cues[1]["asset_audio"]), licensed_path)

    def test_continuous_soundscape_suppresses_short_section_and_inherits_previous(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cue_path = root / "sound-design.json"
            asset_path = root / "bed.wav"
            _write_silence(asset_path)
            sound_design = _continuous_sound_design(asset_path)
            cue_path.write_text(json.dumps(sound_design), encoding="utf-8")

            result = resolve_soundscape(
                cue_path,
                [
                    {"segment_id": "s1", "start_ms": 0, "end_ms": 6000},
                    {"segment_id": "s2", "start_ms": 6000, "end_ms": 8000},
                    {"segment_id": "s3", "start_ms": 8000, "end_ms": 20000},
                ],
            )

            self.assertTrue(result["continuous"])
            self.assertEqual(
                [cue["cue_id"] for cue in result["cues"]],
                ["base", "section-a", "section-b"],
            )
            self.assertEqual(result["cues"][0]["duration_ms"], 20000)
            self.assertEqual(result["cues"][1]["end_ms"], 8000)
            self.assertEqual(
                result["suppressed_section_cues"][0]["cue_id"],
                "section-too-short",
            )


def _sound_design() -> dict:
    common = {
        "kind": "ambience",
        "duration_ms": 1000,
        "gain_db": -24,
        "fade_in_ms": 100,
        "fade_out_ms": 100,
        "loop": False,
        "duck_under_dialogue": True,
        "transcript_label": "soft room tone",
        "editorial_note": "",
        "provenance": {
            "presentation": "illustrative_sound_design",
            "disclosure": "Designed sound.",
        },
    }
    return {
        "contract_version": 1,
        "episode_id": "2013-12.01",
        "sound_design_disclosure": "All sounds are illustrative.",
        "editorial_principles": [],
        "cues": [
            {
                **common,
                "cue_id": "generated-cue",
                "anchor": {
                    "segment_id": "s1",
                    "point": "start",
                    "offset_ms": 0,
                },
                "source": {
                    "type": "generated",
                    "prompt": "Soft room tone.",
                    "generation_duration_ms": 1000,
                },
            },
            {
                **common,
                "cue_id": "licensed-cue",
                "anchor": {
                    "segment_id": "s1",
                    "point": "end",
                    "offset_ms": -500,
                },
                "source": {
                    "type": "licensed",
                    "path": "placeholder.wav",
                    "license": "Example license",
                    "credit": "Example credit",
                },
            },
        ],
    }


def _write_silence(path: Path) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(48000)
        output.writeframes(b"\x00\x00\x00\x00" * 48000)


def _continuous_sound_design(asset_path: Path) -> dict:
    cues = []
    for cue_id, segment_id, coverage_role in (
        ("base", "s1", "base"),
        ("section-a", "s1", "section"),
        ("section-too-short", "s2", "section"),
        ("section-b", "s3", "section"),
    ):
        cues.append(
            {
                "cue_id": cue_id,
                "kind": "ambience",
                "coverage_role": coverage_role,
                "anchor": {
                    "segment_id": segment_id,
                    "point": "start",
                    "offset_ms": 0,
                },
                "duration_ms": 1000,
                "gain_db": -24,
                "fade_in_ms": 100,
                "fade_out_ms": 100,
                "loop": True,
                "duck_under_dialogue": True,
                "transcript_label": cue_id,
                "caption_duration_ms": 1000,
                "editorial_note": "",
                "provenance": {
                    "presentation": "licensed_recording",
                    "disclosure": "Test sound.",
                },
                "source": {
                    "type": "licensed",
                    "path": str(asset_path),
                    "license": "Test-only generated silence",
                    "credit": "Test suite",
                },
            }
        )
    return {
        "contract_version": 1,
        "episode_id": "test-episode",
        "sound_design_disclosure": "Illustrative sounds.",
        "editorial_principles": [],
        "continuous_background": {
            "enabled": True,
            "base_cue_id": "base",
            "minimum_specific_span_ms": 5000,
            "short_span_policy": "inherit_previous",
        },
        "cues": cues,
    }


if __name__ == "__main__":
    unittest.main()
