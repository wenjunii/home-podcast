import copy
import unittest

from home_podcast.single_take_audio import human_confirmed_span_report


class HumanSpanReviewTests(unittest.TestCase):
    def setUp(self):
        before='I wanted a small home with a say in all the choices.'
        self.phrase='That probably tells you something about my need for control.'
        after="I'm comfortable with people finding these ideas a little strange. I don't own a great deal."
        self.text=' '.join((before,self.phrase,after))
        self.job=dict(text=self.text,cache_key='job')
        words=[dict(word=' '+w,start_s=i*.4,end_s=(i+1)*.4) for i,w in enumerate(before.split())]
        self.original=dict(cache_key='job',audio_sha256='audio',asr_model='small',asr_revision='rev',
            segments=[dict(text=before+' That',start_s=0,end_s=18,
                           words=words+[dict(word=' That',start_s=18,end_s=18)]),
                      dict(text=after,start_s=18,end_s=30,words=[])])
        restored=dict(text=self.phrase,start_s=12,end_s=17,
                      words=[dict(word=' '+w,start_s=12+i*.45,end_s=12+(i+1)*.45)
                             for i,w in enumerate(self.phrase.split())])
        self.diagnostic=dict(audio_sha256='audio',original_asr_sha256='original',
            script_prompt_supplied=False,asr_model='small',asr_revision='rev',
            recognized_text=self.text,segments=[dict(text=before),restored,dict(text=after)])
        self.review=dict(decision='recognized_passage_was_spoken',confirmed_by_human=True,
            reviewer='user',user_decision='Yes, I hear the sentence',cache_key='job',
            audio_sha256='audio',original_asr_sha256='original',span_diagnostic_sha256='diagnostic',
            confirmed_spoken_passage=self.phrase,target_segment_index=0,trim_trailing_words=1,
            diagnostic_segment_index=1)

    def resolve(self):
        return human_confirmed_span_report(self.job,self.original,self.review,self.diagnostic,
                                            'original','review','diagnostic')

    def test_use_measured_words_keep_original_and_listening_pending(self):
        original=copy.deepcopy(self.original)
        result=self.resolve()
        self.assertEqual(result['recognized_text'],self.text)
        self.assertEqual(self.original,original)
        self.assertEqual(result['segments'][1],self.diagnostic['segments'][1])
        self.assertEqual(result['content_findings'],[])
        self.assertEqual(result['asr_span_resolution']['listening_approval'],'pending')

    def test_explicit_decision_and_hashes_required(self):
        for key,value in (('confirmed_by_human',False),('reviewer',''),('user_decision',''),
                          ('cache_key','other'),('audio_sha256','other'),
                          ('original_asr_sha256','other'),('span_diagnostic_sha256','other')):
            before=copy.deepcopy(self.review)
            self.review[key]=value
            with self.assertRaises(ValueError):
                self.resolve()
            self.review=before

    def test_no_script_prompt_or_unsupported_recognition(self):
        self.diagnostic['script_prompt_supplied']=True
        with self.assertRaises(ValueError):
            self.resolve()
        self.diagnostic['script_prompt_supplied']=False
        self.diagnostic['recognized_text']+=' Unsupported sentence.'
        with self.assertRaises(ValueError):
            self.resolve()

    def test_cannot_remove_prior_words_or_overlap_following_speech(self):
        self.review['trim_trailing_words']=2
        with self.assertRaises(ValueError):
            self.resolve()
        self.review['trim_trailing_words']=1
        self.diagnostic['segments'][1]['end_s']=18.1
        with self.assertRaises(ValueError):
            self.resolve()

    def test_zero_duration_invented_word_timing_rejected(self):
        self.diagnostic['segments'][1]['words'][0]['end_s']=12
        with self.assertRaises(ValueError):
            self.resolve()


if __name__=='__main__':
    unittest.main()
