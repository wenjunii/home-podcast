from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from home_podcast.storytelling_quality import (
    content_digest, personal_story_findings, require_current_speech_jobs,
    spoken_content_findings, validate_personal_visual_plan,
)
from tests.storytelling_test_support import write_review
from home_podcast.local_audio import _audition_excerpt


class PersonalStoryQualityTests(unittest.TestCase):
    def test_source_commentary_is_not_a_personal_narration(self):
        self.assertIn("spoken_source_commentary", spoken_content_findings({
            "sections": [{"text": "I was there. The source says that it was home."}]}))

    def test_archive_months_and_advertisements_are_blocked(self):
        findings = spoken_content_findings({"sections": [{
            "text": "My blog. March 2009 February 2009 January 2009 December 2008. Buy now!"}]})
        self.assertIn("spoken_archive_month_list", findings)
        self.assertIn("possible_spoken_advertising", findings)

    def test_real_life_dates_are_not_treated_as_archive_entries(self):
        self.assertEqual([], spoken_content_findings({"sections": [{
            "text": "I moved in March 2009. In February 2010 I returned. January 2011 was harder. I went back in December 2012."}]}))

    def test_long_audition_excerpt_does_not_invent_punctuation(self):
        text = "I remember " + "our long walk home " * 40
        excerpt = _audition_excerpt(text, 180)
        self.assertIn(excerpt, text)
        self.assertLessEqual(len(excerpt), 180)

    def test_first_person_company_copy_cannot_pass_without_editorial_review(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / "adaptation.json").write_text(json.dumps({
                "narration_id": "n", "sections": [{"section_id": "001", "text": "We build better homes."}]}))
            (directory / "source-job.json").write_text(json.dumps({"story_text": "We build better homes."}))
            self.assertIn("personal_story_editorial_review_required", personal_story_findings(directory))

    def test_review_and_cached_speech_plan_are_revoked_after_an_edit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            directory = root / "n"
            directory.mkdir()
            adaptation = {"narration_id": "n", "sections": [{
                "section_id": "001", "text": "I remember the road home."}]}
            path = directory / "adaptation.json"
            path.write_text(json.dumps(adaptation))
            write_review(directory)
            self.assertEqual([], personal_story_findings(directory))
            jobs = [{"narration_id": "n", "section_id": "001",
                     "text": adaptation["sections"][0]["text"],
                     "adaptation_sha256": content_digest(adaptation)}]
            config = SimpleNamespace(episodes_dir=root)
            require_current_speech_jobs(config, jobs, audition=False)
            adaptation["sections"][0]["text"] = "I remember a different road."
            path.write_text(json.dumps(adaptation))
            self.assertIn("stale_personal_story_review", personal_story_findings(directory))
            with self.assertRaisesRegex(ValueError, "Personal-story production gate"):
                require_current_speech_jobs(config, jobs, audition=False)
            write_review(directory)
            with self.assertRaisesRegex(ValueError, "Stale speech plan"):
                require_current_speech_jobs(config, jobs, audition=False)

    def test_visuals_need_personal_grounding_but_allow_front_portraits(self):
        adaptation = {"narration_id": "n", "sections": [{
            "section_id": "001", "text": "I waited outside our home."}]}
        scene = {"scene_id": "s", "section_ids": ["001"],
                 "personal_story_excerpt": "I waited outside our home.",
                 "prompt": "Front-facing environmental portrait, 4K photography"}
        validate_personal_visual_plan({"narration_id": "n", "scenes": [scene]}, adaptation)
        scene["personal_story_excerpt"] = "Archives: January 2008"
        with self.assertRaisesRegex(ValueError, "exact spoken excerpt"):
            validate_personal_visual_plan({"narration_id": "n", "scenes": [scene]}, adaptation)


if __name__ == "__main__":
    unittest.main()
