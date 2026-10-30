"""A human decision resolves only the exact false ASR suffix, never the audio."""
import copy
from pathlib import Path
import tempfile
import unittest

from home_podcast.single_take_audio import (effective_asr_path, human_confirmed_outro_report,
                                          sha, write_json)


class HumanOutroReviewTests(unittest.TestCase):
    def setUp(self):
        self.text = ('I grew up in the small house where my family lived together. '
                     'We shared meals and long conversations. I still think about '
                     'those years when I wonder what comes next.')
        self.job = {'text': self.text, 'cache_key': 'current-job'}
        self.original = dict(cache_key='current-job', audio_sha256='audio',
            asr_model='cached-small', asr_revision='revision',
            segments=[dict(text=self.text, start_s=0., end_s=15.),
                      dict(text='Thank you for your time we will see you again.', start_s=15., end_s=15.24)])
        self.diagnostic = dict(audio_sha256='audio', original_asr_sha256='original',
            script_prompt_supplied=False, asr_model='cached-small', asr_revision='revision',
            recognized_text=self.text, segments=[dict(text=self.text)])
        self.review = dict(decision='asr_outro_not_spoken', confirmed_by_human=True,
            reviewer='user', user_decision='Stops after comes next', audio_sha256='audio',
            cache_key='current-job', original_asr_sha256='original',
            closing_diagnostic_sha256='diagnostic', removed_trailing_segments=1,
            confirmed_spoken_ending='comes next')

    def resolve(self):
        return human_confirmed_outro_report(self.job,self.original,self.review,
                                            self.diagnostic,'original','review','diagnostic')

    def test_preserve_original_and_keep_listening_pending(self):
        before=copy.deepcopy(self.original)
        result=self.resolve()
        self.assertEqual(self.original,before)
        self.assertEqual(result['recognized_text'],self.text)
        self.assertEqual(result['segments'],self.original['segments'][:1])
        self.assertEqual(result['content_findings'],[])
        self.assertEqual(result['asr_tail_resolution']['listening_approval'],'pending')

    def test_human_decision_and_all_evidence_hashes_required(self):
        for key,value in (('confirmed_by_human',False),('decision','automatic'),
                          ('audio_sha256','changed'),('cache_key','other'),
                          ('original_asr_sha256','changed'),('closing_diagnostic_sha256','changed'),
                          ('reviewer',''),('user_decision',''),('confirmed_spoken_ending','new ending')):
            original=copy.deepcopy(self.review)
            self.review[key]=value
            with self.assertRaises(ValueError):
                self.resolve()
            self.review=original

    def test_prompted_or_different_closing_recognition_is_rejected(self):
        self.diagnostic['script_prompt_supplied']=True
        with self.assertRaises(ValueError):
            self.resolve()
        self.diagnostic['script_prompt_supplied']=False
        self.diagnostic['recognized_text']+=' Extra words.'
        with self.assertRaises(ValueError):
            self.resolve()

    def test_cannot_remove_normally_timed_or_in_body_speech(self):
        self.original['segments'][-1]['end_s']=20.
        with self.assertRaises(ValueError):
            self.resolve()
        self.original['segments'][-1]['end_s']=15.24
        self.original['segments'][-1]['start_s']=14.9
        with self.assertRaises(ValueError):
            self.resolve()

    def test_effective_report_requires_unchanged_original_and_review(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            audio=directory/'voices-only.wav'
            audio.write_bytes(b'unchanged test recording')
            self.original['audio_sha256']=self.review['audio_sha256']=self.diagnostic['audio_sha256']=sha(audio)
            original=directory/'asr-report.json'
            write_json(original,self.original)
            self.review['original_asr_sha256']=self.diagnostic['original_asr_sha256']=sha(original)
            diagnostic=directory/'asr-ending-diagnostic.json'
            write_json(diagnostic,self.diagnostic)
            self.review['closing_diagnostic_sha256']=sha(diagnostic)
            review=directory/'asr-outro-human-review.json'
            write_json(review,self.review)
            result=human_confirmed_outro_report(self.job,self.original,self.review,self.diagnostic,
                                                sha(original),sha(review),sha(diagnostic))
            resolved=directory/'asr-report-human-reviewed.json'
            write_json(resolved,result)
            self.assertEqual(effective_asr_path(directory,self.job),resolved)
            audio.write_bytes(b'changed recording')
            with self.assertRaises(ValueError):
                effective_asr_path(directory,self.job)


if __name__=='__main__':
    unittest.main()
