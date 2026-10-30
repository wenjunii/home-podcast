from __future__ import annotations

import json
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace

from home_podcast.live_storytelling import (
    _accept_narration_variant,
    _accept_visual_variant,
    _retime_visual_plan,
    create_interpretive_casting_card,
    execute_live_variation,
    prepare_live_variation,
    read_live_control,
    run_live_worker,
    update_live_control,
)
from home_podcast.providers.ollama import OllamaLocalClient
from home_podcast.visual_prompt_runner import TokenCount
from tests.storytelling_test_support import write_review


ROOT = Path(__file__).parents[1]


def _source_job(narration_id="2013-12--story-aaaaaaaaaaaaaaaaaaaaaaaa"):
    excerpt = (
        "I grew up in the Hocking Hills with my grandma and returned every summer."
    )
    return {
        "contract_version": 1,
        "narration_id": narration_id,
        "source_story_id": "story-aaaaaaaaaaaaaaaaaaaaaaaa",
        "source_content_hash": "b" * 64,
        "source_language": "en",
        "adaptation_language": "en",
        "story_text": excerpt,
        "perspective": {
            "preferred_perspective": "first_person_preserved",
            "first_person_evidence": [excerpt],
        },
        "story_card": {
            "locations": [
                {
                    "place": "Hocking Hills",
                    "evidence_excerpt": excerpt,
                }
            ],
            "people": [
                {
                    "name_or_role": "my grandma",
                    "evidence_excerpt": excerpt,
                }
            ],
            "pronunciation_items": ["Hocking Hills"],
        },
        "required_evidence_excerpts": [excerpt],
        "required_gap_disclosures": [],
    }


def _adaptation(narration_id="2013-12--story-aaaaaaaaaaaaaaaaaaaaaaaa"):
    excerpt = (
        "I grew up in the Hocking Hills with my grandma and returned every summer."
    )
    return {
        "contract_version": 1,
        "narration_id": narration_id,
        "source_story_id": "story-aaaaaaaaaaaaaaaaaaaaaaaa",
        "source_content_hash": "b" * 64,
        "title": "Summer Hills",
        "source_language": "en",
        "adaptation_language": "en",
        "perspective_mode": "first_person_preserved",
        "identity_constraints": [],
        "narrator_profile": {
            "personality_tags": ["warm"],
            "emotional_range_tags": ["nostalgic"],
            "energy": "medium",
            "casting_notes": "Personal and unforced.",
        },
        "sections": [
            {
                "section_id": "001",
                "text": (
                    "I grew up in the Hocking Hills with my grandma, and every summer "
                    "I found my way back to those familiar paths and quiet trees."
                ),
                "source_evidence": [
                    {"excerpt": excerpt, "usage": "paraphrase_support"}
                ],
                "delivery": {
                    "emotion": "nostalgic warmth",
                    "intensity": 0.5,
                    "pace": "conversational",
                    "nonverbal": ["breath"],
                    "direction": "Speak gently.",
                },
                "pause_after_ms": 500,
            }
        ],
        "unresolved_gaps": [],
        "adaptation_notes": [],
    }


class LiveStorytellingTests(unittest.TestCase):
    def _config(self, root: Path):
        (root / "config").mkdir()
        (root / "prompts").mkdir()
        (root / "config" / "live_storytelling.json").write_text(
            (ROOT / "config" / "live_storytelling.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        for name in ("live_narration_variation.md", "live_visual_variation.md"):
            (root / "prompts" / name).write_text(
                (ROOT / "prompts" / name).read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        return SimpleNamespace(
            project_root=root,
            work_dir=root / "work",
            episodes_dir=root / "narrations",
        )

    def test_interpretive_cast_is_deterministic_and_separates_location(self):
        live_config = json.loads(
            (ROOT / "config" / "live_storytelling.json").read_text(encoding="utf-8")
        )
        first = create_interpretive_casting_card(
            _adaptation(),
            _source_job(),
            live_config,
            seed=42,
            loop_index=3,
            casting_mode="interpretive",
        )
        changed_job = _source_job()
        changed_job["story_card"]["locations"][0]["place"] = "Lisbon"
        second = create_interpretive_casting_card(
            _adaptation(),
            changed_job,
            live_config,
            seed=42,
            loop_index=3,
            casting_mode="interpretive",
        )

        self.assertEqual(first["cast_id"], second["cast_id"])
        self.assertEqual(first["voice"], second["voice"])
        self.assertFalse(first["identity_claim"])
        self.assertEqual(
            first["trait_provenance"]["accent_profile"]["evidence_status"],
            "artistic_casting",
        )

    def test_explicit_voice_trait_is_locked(self):
        adaptation = _adaptation()
        excerpt = _source_job()["story_text"]
        adaptation["identity_constraints"] = [
            {
                "trait": "narrator_accent",
                "value": "Irish English",
                "evidence_excerpt": excerpt,
            }
        ]
        live_config = json.loads(
            (ROOT / "config" / "live_storytelling.json").read_text(encoding="utf-8")
        )
        card = create_interpretive_casting_card(
            adaptation,
            _source_job(),
            live_config,
            seed=7,
            loop_index=1,
            casting_mode="interpretive",
        )

        self.assertEqual(card["voice"]["accent_profile"], "Irish English")
        self.assertEqual(
            card["trait_provenance"]["accent_profile"]["evidence_status"],
            "source_locked",
        )

    def test_prepare_reports_exact_local_work_and_rejects_third_person(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            narration_id = _adaptation()["narration_id"]
            narration_dir = config.episodes_dir / narration_id
            narration_dir.mkdir(parents=True)
            (narration_dir / "adaptation.json").write_text(
                json.dumps(_adaptation()), encoding="utf-8"
            )
            (narration_dir / "source-job.json").write_text(
                json.dumps(_source_job()), encoding="utf-8"
            )
            write_review(narration_dir)

            result = prepare_live_variation(
                config,
                narration_id,
                profile_name="5090_live",
                loop_index=2,
                seed=99,
            )

            self.assertEqual(result["pending_local_work"]["ollama_narration_calls"], 1)
            self.assertEqual(result["pending_local_work"]["ollama_visual_calls"], 0)
            self.assertEqual(result["pending_local_work"]["qwen_tts_sections"], 1)
            self.assertEqual(result["paid_calls"], 0)

            third_person = _adaptation()
            third_person["perspective_mode"] = "third_person_storyteller"
            (narration_dir / "adaptation.json").write_text(
                json.dumps(third_person), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "first-person"):
                prepare_live_variation(
                    config,
                    narration_id,
                    profile_name="5090_live",
                    loop_index=3,
                )

    def test_prepare_counts_both_switchable_visual_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            narration_id = _adaptation()["narration_id"]
            narration_dir = config.episodes_dir / narration_id
            narration_dir.mkdir(parents=True)
            (narration_dir / "adaptation.json").write_text(
                json.dumps(_adaptation()), encoding="utf-8"
            )
            (narration_dir / "source-job.json").write_text(
                json.dumps(_source_job()), encoding="utf-8"
            )
            write_review(narration_dir)
            paths = []
            for visual_id in ("original", "human_figures"):
                path = root / f"{visual_id}.json"
                path.write_text(
                    json.dumps(
                        {
                            "visual_path": {"id": visual_id},
                            "narration_id": narration_id,
                            "scenes": [{"scene_id": f"{visual_id}-1",
                                        "section_ids": ["001"],
                                        "personal_story_excerpt": "I grew up in the Hocking Hills"}],
                        }
                    ),
                    encoding="utf-8",
                )
                paths.append(path)

            result = prepare_live_variation(
                config,
                narration_id,
                profile_name="5090_live",
                loop_index=2,
                seed=4,
                canonical_visuals_path=paths[0],
                canonical_human_visuals_path=paths[1],
            )

            self.assertEqual(result["pending_local_work"]["ollama_visual_calls"], 2)
            self.assertEqual(result["visual_scene_count"], 2)
            self.assertEqual(
                set(result["canonical"]["visuals"]),
                {"original", "human_figures"},
            )

    def test_narration_gate_preserves_source_evidence_and_protected_terms(self):
        canonical = _adaptation()
        source = _source_job()
        card = {
            "cast_id": "cast-test",
        }
        request = {
            "variant_id": "variant-test",
            "casting_card": card,
            "canonical": {"adaptation": "canonical.json"},
            "seeds": {"narration": 123},
        }
        result = {
            "sections": [
                {
                    "section_id": "001",
                    "text": (
                        "I was raised around Hocking Hills with my grandma, and each "
                        "summer I returned to the familiar paths and quiet trees."
                    ),
                    "delivery": canonical["sections"][0]["delivery"],
                    "pause_after_ms": 650,
                }
            ]
        }

        accepted = _accept_narration_variant(result, canonical, source, request)

        self.assertEqual(
            accepted["sections"][0]["source_evidence"],
            canonical["sections"][0]["source_evidence"],
        )
        self.assertEqual(accepted["variant_id"], "variant-test")
        result["sections"][0]["text"] = "I returned to some quiet trees."
        with self.assertRaisesRegex(ValueError, "protected term"):
            _accept_narration_variant(result, canonical, source, request)

    def test_visual_gate_preserves_timing_and_cast(self):
        plan = {
            "duration_ms": 20000,
            "scenes": [
                {
                    "scene_id": "visual-001",
                    "start_ms": 0,
                    "end_ms": 20000,
                    "duration_ms": 20000,
                    "crossfade_in_ms": 0,
                    "crossfade_out_ms": 5000,
                    "grounding": {"locations": []},
                    "prompt": {"chunks": [], "seed": 1},
                }
            ],
        }
        prompt = (
            "4K photography, front-facing environmental portrait of a reflective "
            "adult beside a wooded hillside home, steady eye contact, natural window "
            "light, familiar footpath, worn family objects, restrained cinematic color, "
            "authentic materials, intimate documentary framing, subtle archival grain, "
            "quiet emotional presence, detailed skin texture, softly layered background"
        )
        request = {
            "variant_id": "variant-test",
            "casting_card": {"cast_id": "cast-test"},
            "seeds": {"image": 5, "visual_prompt": 6},
        }
        result = {
            "cast_id": "cast-test",
            "scenes": [{"scene_id": "visual-001", "prompt": prompt}],
        }

        accepted = _accept_visual_variant(
            result,
            plan,
            request,
            lambda _text: TokenCount(maximum=70, by_tokenizer={"test": 70}),
        )

        self.assertEqual(accepted["scenes"][0]["start_ms"], 0)
        self.assertEqual(accepted["scenes"][0]["end_ms"], 20000)
        self.assertEqual(accepted["live_variation"]["cast_id"], "cast-test")

    def test_visual_retiming_follows_local_speech_duration(self):
        plan = {
            "duration_ms": 20000,
            "scenes": [
                {
                    "scene_id": "v1",
                    "start_ms": 0,
                    "end_ms": 10000,
                    "duration_ms": 10000,
                    "crossfade_in_ms": 0,
                    "crossfade_out_ms": 5000,
                },
                {
                    "scene_id": "v2",
                    "start_ms": 10000,
                    "end_ms": 20000,
                    "duration_ms": 10000,
                    "crossfade_in_ms": 5000,
                    "crossfade_out_ms": 5000,
                },
            ],
        }
        timeline = {
            "duration_ms": 30000,
            "sections": [
                {
                    "section_id": "001",
                    "start_ms": 0,
                    "speech_end_ms": 29000,
                    "end_ms": 30000,
                    "text": "I remember home.",
                }
            ],
        }

        retimed = _retime_visual_plan(plan, timeline)

        self.assertEqual(retimed["duration_ms"], 30000)
        self.assertEqual(retimed["scenes"][0]["end_ms"], 15000)
        self.assertEqual(retimed["scenes"][1]["start_ms"], 15000)
        self.assertEqual(retimed["scenes"][1]["end_ms"], 30000)

    def test_file_control_keeps_3080_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self._config(Path(directory))
            control = update_live_control(
                config,
                {"profile": "3080_safe", "enabled": False, "fixed_seed": 8},
            )

            self.assertFalse(control["enabled"])
            self.assertEqual(read_live_control(config)["fixed_seed"], 8)

            worker = run_live_worker(config, once=True)
            status = json.loads(Path(worker["status"]).read_text(encoding="utf-8"))
            self.assertEqual(status["state"], "disabled")
            self.assertIsNone(worker["last_result"])

    def test_execute_promotes_only_after_local_audio_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._config(root)
            narration_id = _adaptation()["narration_id"]
            narration_dir = config.episodes_dir / narration_id
            narration_dir.mkdir(parents=True)
            (narration_dir / "adaptation.json").write_text(
                json.dumps(_adaptation()), encoding="utf-8"
            )
            (narration_dir / "source-job.json").write_text(
                json.dumps(_source_job()), encoding="utf-8"
            )
            write_review(narration_dir)
            request = prepare_live_variation(
                config,
                narration_id,
                profile_name="5090_live",
                loop_index=1,
                seed=12,
            )
            canonical = _adaptation()["sections"][0]

            class FakeOllama:
                def generate_json(self, *_args, **_kwargs):
                    return SimpleNamespace(
                        value={
                            "sections": [
                                {
                                    "section_id": "001",
                                    "text": (
                                        "I was raised in Hocking Hills with my grandma, "
                                        "and every summer I returned to those familiar "
                                        "paths and quiet trees."
                                    ),
                                    "delivery": canonical["delivery"],
                                    "pause_after_ms": 500,
                                }
                            ]
                        },
                        model="gemma4:12b",
                        done_reason="stop",
                        prompt_eval_count=10,
                        eval_count=20,
                        total_duration_ns=30,
                    )

            class FakeSpeech:
                def render(self, adaptation, _casting, output_dir, *, speech_seed):
                    output_dir.mkdir(parents=True)
                    audio = output_dir / "voices-only.wav"
                    with wave.open(str(audio), "wb") as handle:
                        handle.setnchannels(1)
                        handle.setsampwidth(2)
                        handle.setframerate(8000)
                        handle.writeframes(b"\x00\x00" * 800)
                    timeline = output_dir / "timeline.json"
                    timeline.write_text(
                        json.dumps(
                            {
                                "duration_ms": 100,
                                "sections": [
                                    {
                                        "section_id": "001",
                                        "start_ms": 0,
                                        "speech_end_ms": 100,
                                        "end_ms": 100,
                                        "text": adaptation["sections"][0]["text"],
                                    }
                                ],
                            }
                        ),
                        encoding="utf-8",
                    )
                    (output_dir / "captions.vtt").write_text("WEBVTT\n", encoding="utf-8")
                    (output_dir / "captions.srt").write_text("", encoding="utf-8")
                    return SimpleNamespace(
                        audio_path=audio,
                        timeline_path=timeline,
                        sections=1,
                    )

            result = execute_live_variation(
                config,
                Path(request["request"]),
                ollama_client=FakeOllama(),
                speech_renderer=FakeSpeech(),
                visual_variation=False,
            )

            self.assertEqual(result["status"], "ready")
            self.assertEqual(result["calls"]["ollama"], 1)
            pointer = json.loads(
                (config.work_dir / "runtime" / "current.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(pointer["variant_id"], result["variant_id"])
            self.assertTrue(Path(result["assets"]["audio"]).is_file())

    def test_ollama_adapter_rejects_nonlocal_endpoint(self):
        with self.assertRaisesRegex(ValueError, "loopback"):
            OllamaLocalClient(base_url="https://example.com", model="gemma4:12b")

    def test_overlong_audio_does_not_replace_last_ready_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self._config(Path(directory))
            config.production_mode = "self_narrated_storytelling"
            config.target_minutes_max = 5
            narration_id = _adaptation()["narration_id"]
            narration_dir = config.episodes_dir / narration_id
            (narration_dir / "audio").mkdir(parents=True)
            (narration_dir / "adaptation.json").write_text(json.dumps(_adaptation()), encoding="utf-8")
            (narration_dir / "source-job.json").write_text(json.dumps(_source_job()), encoding="utf-8")
            write_review(narration_dir)
            audio = narration_dir / "audio" / "voices-only.wav"
            with wave.open(str(audio), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(10)
                handle.writeframes(b"\x00\x00" * 3001)
            request = prepare_live_variation(
                config, narration_id, profile_name="3080_safe", loop_index=1, seed=12,
            )
            pointer = config.work_dir / "runtime" / "current.json"
            pointer.write_text('{"variant_id": "last-known-good"}', encoding="utf-8")
            previous = pointer.read_bytes()
            with self.assertRaisesRegex(ValueError, "300-second limit"):
                execute_live_variation(config, Path(request["request"]))
            self.assertEqual(pointer.read_bytes(), previous)
            self.assertTrue(audio.is_file())


if __name__ == "__main__":
    unittest.main()
