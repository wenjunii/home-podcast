from __future__ import annotations

import json
import math
import shutil
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from home_podcast.audio import (
    _sound_bus,
    render_dialogue_episode_audio,
    render_episode_audio,
    render_soundscape_audio,
)


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "ffmpeg and ffprobe are required for the audio integration test",
)
class AudioRenderTests(unittest.TestCase):
    def test_sound_bus_does_not_attenuate_active_cues_by_future_inputs(self) -> None:
        filters: list[str] = []

        label = _sound_bus(filters, ["[first]", "[future]"], "scene_bus")

        self.assertEqual(label, "[scene_bus]")
        self.assertEqual(
            filters,
            [
                "[first][future]"
                "amix=inputs=2:dropout_transition=0,"
                "volume=2[scene_bus]"
            ],
        )

    def test_preserves_speech_only_render_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            voice = root / "voice.wav"
            _write_tone(voice, 440)
            jobs_path = _write_jobs(root, voice)

            timeline = render_episode_audio(
                jobs_path,
                root / "work",
                root / "output",
            )
            self.assertEqual(timeline["sound_cues"], [])
            self.assertIsNone(timeline["sound_design"])
            self.assertTrue(Path(timeline["master_audio"]).is_file())
            self.assertTrue(
                Path(
                    timeline["tracks"]["voices_only"]["distribution_audio"]
                ).is_file()
            )
            self.assertNotIn("soundscape_only", timeline["tracks"])

    def test_mixes_optional_ducked_and_plain_sound_cues(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            voice = root / "voice.wav"
            effect = root / "effect.wav"
            _write_tone(voice, 440)
            _write_tone(effect, 220, amplitude=50)
            jobs_path = _write_jobs(root, voice)
            sound_design_path = root / "sound-design.json"
            sound_design_path.write_text(
                json.dumps(
                    {
                        "contract_version": 1,
                        "episode_id": "test-episode",
                        "sound_design_disclosure": "Illustrative sounds.",
                        "editorial_principles": [],
                        "cues": [
                            _licensed_cue("ducked", effect, True, 0),
                            _licensed_cue("plain", effect, False, 250),
                        ],
                    }
                ),
                encoding="utf-8",
            )

            timeline = render_episode_audio(
                jobs_path,
                root / "work",
                root / "output",
                sound_design_path=sound_design_path,
            )
            self.assertEqual(len(timeline["sound_cues"]), 2)
            self.assertTrue(Path(timeline["master_audio"]).is_file())
            self.assertTrue(Path(timeline["distribution_audio"]).is_file())
            self.assertTrue(
                Path(
                    timeline["tracks"]["voices_only"]["distribution_audio"]
                ).is_file()
            )
            self.assertTrue(
                Path(
                    timeline["tracks"]["soundscape_only"]["distribution_audio"]
                ).is_file()
            )
            self.assertTrue(
                Path(
                    timeline["tracks"]["combined_preview"]["distribution_audio"]
                ).is_file()
            )
            self.assertEqual(
                timeline["sound_design"]["disclosure"], "Illustrative sounds."
            )

    def test_continuous_soundscape_tracks_match_voice_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            voice = root / "voice.wav"
            effect = root / "effect.wav"
            _write_tone(voice, 440)
            _write_tone(effect, 220, amplitude=50)
            jobs_path = _write_jobs(root, voice)
            sound_design_path = root / "sound-design.json"
            base = _licensed_cue("base", effect, True, 0)
            base["coverage_role"] = "base"
            base["loop"] = True
            section = _licensed_cue("section", effect, True, 0)
            section["coverage_role"] = "section"
            section["loop"] = True
            sound_design_path.write_text(
                json.dumps(
                    {
                        "contract_version": 1,
                        "episode_id": "test-episode",
                        "sound_design_disclosure": "Illustrative sounds.",
                        "editorial_principles": [],
                        "continuous_background": {
                            "enabled": True,
                            "base_cue_id": "base",
                            "minimum_specific_span_ms": 1000,
                            "short_span_policy": "inherit_previous",
                        },
                        "cues": [base, section],
                    }
                ),
                encoding="utf-8",
            )

            timeline = render_episode_audio(
                jobs_path,
                root / "work",
                root / "output",
                sound_design_path=sound_design_path,
            )
            voices = Path(
                timeline["tracks"]["voices_only"]["distribution_audio"]
            )
            sounds = Path(
                timeline["tracks"]["soundscape_only"]["distribution_audio"]
            )
            self.assertTrue(voices.is_file())
            self.assertTrue(sounds.is_file())
            self.assertTrue(timeline["soundscape_coverage"]["continuous"])
            self.assertEqual(timeline["sound_cues"][0]["duration_ms"], 1000)
            self.assertEqual(timeline["sound_cues"][1]["duration_ms"], 1000)
            self.assertGreater(
                _max_sample(
                    Path(
                        timeline["tracks"]["soundscape_only"]["master_audio"]
                    )
                ),
                500,
            )

    def test_renders_contextual_dialogue_from_provider_timestamps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dialogue = root / "dialogue.wav"
            _write_tone(dialogue, 440)
            timing = root / "dialogue.timestamps.json"
            timing.write_text(
                json.dumps(
                    {
                        "voice_segments": [
                            {
                                "dialogue_input_index": 0,
                                "start_time_seconds": 0.1,
                                "end_time_seconds": 0.4,
                            },
                            {
                                "dialogue_input_index": 1,
                                "start_time_seconds": 0.5,
                                "end_time_seconds": 0.9,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            jobs_path = root / "dialogue-jobs.jsonl"
            jobs_path.write_text(
                json.dumps(
                    {
                        "episode_id": "test-dialogue-episode",
                        "chunk_id": "chunk-001",
                        "cache_key": "dialogue",
                        "output_audio": str(dialogue),
                        "timestamp_data": str(timing),
                        "inputs": [
                            {
                                "segment_id": "m1-s001",
                                "speaker": "curious_guide",
                                "display_name": "Maya",
                                "accent": "American",
                                "text": "A recovered home?",
                                "source_story_ids": ["story-1"],
                            },
                            {
                                "segment_id": "m1-s002",
                                "speaker": "archive_nerd",
                                "display_name": "Theo",
                                "accent": "British",
                                "text": "Let's look closer.",
                                "source_story_ids": ["story-1"],
                            },
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            timeline = render_dialogue_episode_audio(
                jobs_path,
                root / "work",
                root / "output",
            )

            self.assertEqual(timeline["duration_ms"], 1000)
            self.assertEqual(timeline["segments"][0]["start_ms"], 100)
            self.assertEqual(timeline["segments"][0]["end_ms"], 400)
            self.assertEqual(timeline["segments"][1]["start_ms"], 500)
            self.assertEqual(timeline["segments"][1]["end_ms"], 900)
            self.assertEqual(
                timeline["segments"][1]["dialogue_chunk_id"],
                "chunk-001",
            )
            self.assertTrue(
                Path(
                    timeline["tracks"]["voices_only"]["distribution_audio"]
                ).is_file()
            )

    def test_renders_soundscape_against_reviewed_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            voice = root / "voice.wav"
            effect = root / "effect.wav"
            _write_tone(voice, 440)
            _write_tone(effect, 220, amplitude=50)
            timeline_path = root / "timeline.json"
            timeline_path.write_text(
                json.dumps(
                    {
                        "episode_id": "test-episode",
                        "duration_ms": 1000,
                        "segments": [
                            {
                                "segment_id": "s1",
                                "start_ms": 0,
                                "end_ms": 1000,
                                "text": "Reviewed speech.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            sound_design_path = root / "sound-design.json"
            sound_design_path.write_text(
                json.dumps(
                    {
                        "contract_version": 1,
                        "episode_id": "test-episode",
                        "sound_design_disclosure": "Illustrative sounds.",
                        "editorial_principles": [],
                        "cues": [
                            _licensed_cue("scene", effect, True, 0),
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = render_soundscape_audio(
                timeline_path,
                sound_design_path,
                root / "work",
                root / "output",
                voices_audio_path=voice,
            )

            self.assertEqual(result["duration_ms"], 1000)
            self.assertTrue(
                Path(
                    result["tracks"]["soundscape_only"]["distribution_audio"]
                ).is_file()
            )
            self.assertTrue(
                Path(
                    result["tracks"]["combined_preview"]["distribution_audio"]
                ).is_file()
            )
            self.assertFalse((root / "output" / "test-episode-timeline.json").exists())


def _licensed_cue(cue_id: str, path: Path, duck: bool, offset_ms: int) -> dict:
    return {
        "cue_id": cue_id,
        "kind": "spot",
        "anchor": {
            "segment_id": "s1",
            "point": "start",
            "offset_ms": offset_ms,
        },
        "duration_ms": 500,
        "gain_db": -24,
        "fade_in_ms": 50,
        "fade_out_ms": 100,
        "loop": False,
        "duck_under_dialogue": duck,
        "transcript_label": "soft tone",
        "editorial_note": "",
        "provenance": {
            "presentation": "licensed_recording",
            "disclosure": "Test sound.",
        },
        "source": {
            "type": "licensed",
            "path": str(path),
            "license": "Test-only generated tone",
            "credit": "Test suite",
        },
    }


def _write_jobs(root: Path, voice: Path) -> Path:
    jobs_path = root / "tts.jsonl"
    jobs_path.write_text(
        json.dumps(
            {
                "episode_id": "test-episode",
                "segment_id": "s1",
                "speaker": "curious_guide",
                "text": "Test line.",
                "source_story_ids": [],
                "pause_after_ms": 0,
                "cache_key": "voice",
                "output_audio": str(voice),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return jobs_path


def _write_tone(path: Path, frequency: int, *, amplitude: int = 5000) -> None:
    frame_rate = 48000
    frames = bytearray()
    for frame in range(frame_rate):
        sample = round(
            amplitude * math.sin(2 * math.pi * frequency * frame / frame_rate)
        )
        packed = struct.pack("<h", sample)
        frames.extend(packed)
        frames.extend(packed)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(frame_rate)
        output.writeframes(frames)


def _max_sample(path: Path) -> int:
    with wave.open(str(path), "rb") as audio:
        frames = audio.readframes(audio.getnframes())
    samples = struct.unpack(f"<{len(frames) // 2}h", frames)
    return max(abs(sample) for sample in samples)


if __name__ == "__main__":
    unittest.main()
