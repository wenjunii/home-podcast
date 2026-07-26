from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from home_podcast.config import ProjectConfig
from home_podcast.providers.capriole import CaprioleResponse
from home_podcast.visual_prompt_runner import (
    TokenCount,
    _validate_result,
    generate_visual_prompt_jobs,
    import_visual_prompt_results,
)


class _FakeClient:
    model = "anthropic/claude-opus-4-6"
    api_key_env = "TEST_VISUAL_KEY"

    def __init__(self, result: dict[str, object]) -> None:
        self.result = result
        self.calls = 0

    def complete(self, input_text: str) -> CaprioleResponse:
        self.calls += 1
        return CaprioleResponse(
            request_id="visual-request-1",
            model=self.model,
            text=json.dumps(self.result),
            usage={"input_tokens": 100, "output_tokens": 80},
        )


def _count_70(text: str) -> TokenCount:
    return TokenCount(
        maximum=70,
        by_tokenizer={"tokenizer": 69, "tokenizer_2": 70},
    )


def _job() -> dict[str, object]:
    return {
        "contract_version": 1,
        "episode_id": "2013-12.01",
        "scene_id": "visual-001",
        "start_ms": 0,
        "end_ms": 20_000,
        "duration_ms": 20_000,
        "transcript": "A young man writes from Cambridge.",
        "source_story_ids": ["story-a"],
        "source_evidence": [
            {
                "story_id": "story-a",
                "story_text": (
                    "In Cambridge in 1859, a young man wrote that leaving "
                    "home was not really leaving home."
                ),
            }
        ],
        "requirements": {"maximum_content_tokens_per_chunk": 75},
    }


def _result() -> dict[str, object]:
    return {
        "scene_id": "visual-wrong",
        "visual_intent": "An indirect, historically grounded portrait of departure.",
        "locations": [
            {
                "name": "Cambridge",
                "role": "setting",
                "historical_period": "1859",
                "story_id": "story-a",
                "evidence_excerpt": "Cambridge in 1859",
                "confidence": "explicit",
            }
        ],
        "identity_claims": [
            {
                "attribute": "gender",
                "value": "young man",
                "story_id": "story-a",
                "evidence_excerpt": "a young man",
                "confidence": "explicit",
            }
        ],
        "unknown_identity_attributes": ["race", "ethnicity", "nationality"],
        "camera_policy": "Back view to avoid inventing unsupported appearance.",
        "prompt_chunks": [
            {
                "role": "narrative",
                "text": "A detailed evidence-grounded documentary photograph.",
                "weight": 1.0,
            }
        ],
        "seed": 20131201,
        "sensitivity_notes": [],
        "editorial_review_required": True,
    }


def _plan() -> dict[str, object]:
    return {
        "contract_version": 1,
        "episode_id": "2013-12.01",
        "duration_ms": 20_000,
        "master_track": "voices_only",
        "prompt_policy": {"model_id": "test-sdxl"},
        "grounding_policy": {},
        "captions": [],
        "scenes": [
            {
                "scene_id": "visual-001",
                "start_ms": 0,
                "end_ms": 20_000,
                "duration_ms": 20_000,
                "source_story_ids": ["story-a"],
                "grounding": {
                    "location_status": "pending_evidence_review",
                    "locations": [],
                    "identity_status": "pending_evidence_review",
                    "identity_claims": [],
                },
                "prompt": {
                    "status": "pending_grounded_generation",
                    "chunks": [
                        {
                            "role": "narrative",
                            "text": "fallback",
                            "weight": 1.0,
                        }
                    ],
                    "seed": 1,
                },
            }
        ],
    }


class VisualPromptRunnerTests(unittest.TestCase):
    def test_validates_verbatim_grounding_and_exact_token_count(self) -> None:
        result = _validate_result(_result(), _job(), _count_70)
        self.assertEqual(result["scene_id"], "visual-001")
        self.assertEqual(
            result["prompt_chunks"][0]["content_token_count"],
            70,
        )
        self.assertEqual(
            result["prompt_chunks"][0]["content_token_counts"]["tokenizer_2"],
            70,
        )
        self.assertTrue(result["editorial_review_required"])

    def test_rejects_nonverbatim_location_evidence(self) -> None:
        result = _result()
        result["locations"][0]["evidence_excerpt"] = "a city beside the river"
        with self.assertRaisesRegex(ValueError, "not verbatim"):
            _validate_result(result, _job(), _count_70)

    def test_discards_repository_metadata_as_nonphysical_location(self) -> None:
        result = _result()
        result["locations"].append(
            {
                "name": "Internet Archive (digital context)",
                "role": "setting",
                "historical_period": "2013",
                "story_id": "story-a",
                "evidence_excerpt": "sitting as a raw text file on the Internet Archive",
                "confidence": "explicit",
            }
        )
        validated = _validate_result(result, _job(), _count_70)
        self.assertEqual(len(validated["locations"]), 1)
        self.assertTrue(
            any(
                "repository" in note
                for note in validated["sensitivity_notes"]
            )
        )

    def test_snaps_punctuation_variant_to_exact_source_excerpt(self) -> None:
        job = _job()
        job["source_evidence"][0]["story_text"] = (
            "Cambridge in 1859. Max’s fair hair caught the light."
        )
        result = _result()
        result["identity_claims"][0]["evidence_excerpt"] = "Max's fair hair"
        validated = _validate_result(result, job, _count_70)
        claim = validated["identity_claims"][0]
        self.assertEqual(claim["evidence_excerpt"], "Max’s fair hair")
        self.assertEqual(claim["evidence_match"], "source_snapped_punctuation")
        revalidated = _validate_result(validated, job, _count_70)
        self.assertEqual(
            revalidated["identity_claims"][0]["evidence_match"],
            "source_snapped_punctuation",
        )

    def test_snaps_only_high_confidence_same_story_evidence(self) -> None:
        job = _job()
        job["source_evidence"][0]["story_text"] = (
            "A young man had only been in Kenya for about 5 months "
            "and was still learning."
        )
        result = _result()
        result["locations"][0]["name"] = "Kenya"
        result["locations"][0]["evidence_excerpt"] = (
            "We've only been in Kenya for about 5 months"
        )
        validated = _validate_result(result, job, _count_70)
        claim = validated["locations"][0]
        self.assertEqual(
            claim["evidence_excerpt"],
            "only been in Kenya for about 5 months",
        )
        self.assertEqual(claim["evidence_match"], "high_confidence_source_snap")

    def test_rejects_prompt_over_token_limit(self) -> None:
        def count_76(text: str) -> TokenCount:
            return TokenCount(76, {"tokenizer": 75, "tokenizer_2": 76})

        with self.assertRaisesRegex(ValueError, "measured \\[76\\]"):
            _validate_result(_result(), _job(), count_76)

    def test_selects_longest_valid_prompt_candidate(self) -> None:
        result = _result()
        result["prompt_chunks"] = [
            {"role": "narrative", "text": "short", "weight": 1.0},
            {"role": "narrative", "text": "longest", "weight": 1.0},
            {"role": "narrative", "text": "too long", "weight": 1.0},
        ]

        def count_candidates(text: str) -> TokenCount:
            counts = {"short": 69, "longest": 75, "too long": 82}
            count = counts[text]
            return TokenCount(count, {"tokenizer": count})

        validated = _validate_result(result, _job(), count_candidates)
        self.assertEqual(
            validated["prompt_chunks"][0]["text"],
            "longest",
        )
        self.assertEqual(
            validated["prompt_chunks"][0]["content_token_count"],
            75,
        )

    def test_trims_slightly_overlong_candidate_locally(self) -> None:
        result = _result()
        result["prompt_chunks"] = [
            {
                "role": "narrative",
                "text": "one two three four five six",
                "weight": 1.0,
            }
        ]

        def count_candidate(text: str) -> TokenCount:
            count = 70 + len(text.split())
            return TokenCount(count, {"tokenizer": count})

        validated = _validate_result(result, _job(), count_candidate)
        chunk = validated["prompt_chunks"][0]
        self.assertEqual(chunk["content_token_count"], 75)
        self.assertEqual(chunk["local_repair"]["method"], "trim_trailing_words")
        revalidated = _validate_result(validated, _job(), count_candidate)
        self.assertEqual(
            revalidated["prompt_chunks"][0]["local_repair"]["method"],
            "trim_trailing_words",
        )

    def test_maps_unknown_identity_alias(self) -> None:
        result = _result()
        result["unknown_identity_attributes"] = [
            "race",
            "age_at_time_of_speech",
            "gender of narrator",
            "age of daughter",
        ]
        validated = _validate_result(result, _job(), _count_70)
        self.assertEqual(
            validated["unknown_identity_attributes"],
            ["race", "age", "gender"],
        )

    def test_dry_run_makes_no_provider_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config, jobs_path, visuals_path = self._fixture(Path(directory))
            client = _FakeClient(_result())
            report = generate_visual_prompt_jobs(
                config,
                jobs_path,
                visuals_path,
                client=client,
                token_counter=_count_70,
            )
            self.assertEqual(client.calls, 0)
            self.assertEqual(report["api_calls_pending"], 1)
            self.assertEqual(report["applied"], 0)
            self.assertEqual(
                json.loads(visuals_path.read_text(encoding="utf-8"))["scenes"][0][
                    "prompt"
                ]["status"],
                "pending_grounded_generation",
            )

    def test_paid_run_requires_call_ceiling(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config, jobs_path, visuals_path = self._fixture(Path(directory))
            with self.assertRaisesRegex(ValueError, "--max-calls"):
                generate_visual_prompt_jobs(
                    config,
                    jobs_path,
                    visuals_path,
                    execute=True,
                    client=_FakeClient(_result()),
                    token_counter=_count_70,
                )

    def test_paid_run_caches_and_applies_valid_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config, jobs_path, visuals_path = self._fixture(Path(directory))
            client = _FakeClient(_result())
            os.environ[client.api_key_env] = "unit-test-only"
            try:
                report = generate_visual_prompt_jobs(
                    config,
                    jobs_path,
                    visuals_path,
                    execute=True,
                    max_calls=1,
                    client=client,
                    token_counter=_count_70,
                )
            finally:
                os.environ.pop(client.api_key_env, None)
            self.assertEqual(client.calls, 1)
            self.assertEqual(report["generated"], 1)
            self.assertEqual(report["applied"], 1)
            self.assertTrue(report["completed"])
            plan = json.loads(visuals_path.read_text(encoding="utf-8"))
            self.assertEqual(
                plan["scenes"][0]["prompt"]["status"],
                "generated_pending_editorial_review",
            )
            self.assertEqual(
                plan["scenes"][0]["grounding"]["location_status"],
                "machine_verified_evidence",
            )

            cached_client = _FakeClient(_result())
            cached_report = generate_visual_prompt_jobs(
                config,
                jobs_path,
                visuals_path,
                client=cached_client,
                token_counter=_count_70,
            )
            self.assertEqual(cached_client.calls, 0)
            self.assertEqual(cached_report["cached"], 1)
            self.assertEqual(cached_report["api_calls_pending"], 0)

    def test_imports_codex_authored_prompt_without_provider_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, jobs_path, visuals_path = self._fixture(root)
            input_path = root / "codex-visual-results.jsonl"
            authored_result = _result()
            authored_result["scene_id"] = "visual-001"
            input_path.write_text(
                json.dumps(authored_result, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            report = import_visual_prompt_results(
                config,
                input_path,
                jobs_path,
                visuals_path,
                model_label="codex-test",
                token_counter=_count_70,
            )
            self.assertEqual(report["network_calls"], 0)
            self.assertEqual(report["applied"], 1)
            self.assertTrue(report["completed"])
            plan = json.loads(visuals_path.read_text(encoding="utf-8"))
            self.assertEqual(
                plan["visual_prompt_generation"]["provider"],
                "codex_interactive",
            )
            self.assertEqual(
                plan["visual_prompt_generation"]["model"],
                "codex-test",
            )

    @staticmethod
    def _fixture(root: Path) -> tuple[ProjectConfig, Path, Path]:
        (root / "prompts").mkdir(parents=True)
        (root / "prompts" / "visual_prompt_writer.md").write_text(
            "Write a grounded prompt.",
            encoding="utf-8",
        )
        config_path = root / "podcast.json"
        config_path.write_text(
            json.dumps(
                {
                    "project_name": "Test",
                    "exports_dir": "exports",
                    "visual_provider": {
                        "type": "capriole",
                        "endpoint": "https://example.test/v1/messages",
                        "model": "anthropic/claude-opus-4-6",
                        "api_key_env": "TEST_VISUAL_KEY",
                    },
                }
            ),
            encoding="utf-8",
        )
        config = ProjectConfig.load(config_path)
        config.ensure_runtime_directories()
        jobs_path = root / "jobs.jsonl"
        jobs_path.write_text(
            json.dumps(_job(), ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        visuals_path = root / "visuals.json"
        visuals_path.write_text(
            json.dumps(_plan(), ensure_ascii=False),
            encoding="utf-8",
        )
        return config, jobs_path, visuals_path


if __name__ == "__main__":
    unittest.main()
