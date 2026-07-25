# Speech provider research

Reviewed July 25, 2026 for an English-first, three-host rotating-cast podcast with
occasional source-language fragments. Prices and preview status can change, so
recheck them immediately before purchasing production capacity.

## Recommendation

ElevenLabs Eleven v3 is selected for the pilot implementation. The broader
shortlist remains useful if later rotating-cast voices fail listening review:

1. ElevenLabs Eleven v3
2. Hume Octave 2
3. Google Gemini 3.1 Flash TTS Preview
4. Cartesia Sonic 3.5

ElevenLabs was selected because Eleven v3 directly supports
multi-speaker dialogue, expressive delivery, and more than 70 languages. Hume
is the strongest alternative for acting direction and emotional continuity.
Cartesia is the safest broad-language fallback for source fragments and an
economical production benchmark. Gemini is a valuable podcast-oriented
contender, but its current TTS model is preview software and supports at most
two speakers in a single request.

The pilot voices passed their audition. New roster candidates must still be
blind-scored before their voice IDs are added to the rotation.

The project now uses an ElevenLabs Creator subscription with 121,616 monthly
credits and 192 kbps API output. Community Voice Library voices are available
through the API on this paid tier. Nine English-verified candidates are saved
for audition across Canadian, Chinese-influenced, French-influenced, Indian,
Irish, Nigerian, Scottish, South African, and Spanish-influenced English.
Every candidate has a 730-day availability notice and a 1x credit rate.

## Current pilot audition

The first casting pass uses three deliberately distinct default voices:

| Host | Approved pilot voice | Audition focus |
| --- | --- | --- |
| Maya | Bella (`hpp4J3VqNfWAUOO0d1Us`) | Warm welcome, light humor, curiosity, and a restrained close |
| Theo | Roger (`CwhRBWXzGAHq8TQ4Fs17`) | Clear archive explanation, dry warmth, and a serious close |
| Lina | Lily (`pFZP5JQG7iQjIQuC4Bku`) | Cross-cultural observation, intimacy, and emotional restraint |

The source-grounded audition contract is
`episodes/2013-12.01/voice-audition.json`. One API pass used 1,797 input
characters across three calls, approximately $0.18 at the published
$0.10-per-1,000-character rate. The level-matched listening copies total
118.24 seconds and remain in the ignored local directory
`work/tts/audition-2013-12.01/`.

The Eleven v3 TTS endpoint rejected `previous_text` and `next_text` during the
live preflight, so the adapter omits those generic endpoint fields for this
model. This matters for production: ElevenLabs also warns that very short v3
prompts are less consistent. The audition therefore uses one long,
multi-delivery passage per host.

The first follow-up continuity audition rendered 10 short turns independently.
It preserved caching granularity but sounded too flat because Eleven v3 could
not hear the other speakers' turns as context. It has been superseded by an
eight-turn Text-to-Dialogue audition that keeps all three hosts, humor, a tonal
shift, an exact quotation, and nonverbal reactions in one request.

Natural and Creative versions use the same 1,760 rendered characters and differ
only in stability. Natural runs 118.05 seconds and favors consistency. Creative
runs 115.15 seconds and permits broader emotion with a higher artifact risk.
A Creative+ follow-up runs 115.41 seconds with stronger direction and moderate
style exaggeration. Creative+ is selected for the pilot. The full 128-turn
script should use contextual dialogue chunks that preserve this performance
profile.

## Accent-aware rotation

The production roster currently supports American, British, and Australian
voices. The casting algorithm maximizes distinct accents within each valid
three-person lineup, then uses a deterministic episode hash as the tie-break.
Once saved, an episode cast is immutable.

The broader candidate pool is deliberately staged outside the production
roster. Metadata screening requires verified English, at least a one-year
availability notice, and no custom credit multiplier. The same-script audition
then tests a light opening, a serious turn, archive uncertainty, emotional
restraint, and multilingual pronunciation. No accent is synthesized through
an imitation instruction.

Community voices remain a supply-chain dependency. Availability notice reduces
but does not eliminate replacement risk. ElevenLabs also states that its
current default voices expire on December 31, 2026, so future production should
migrate approved hosts to stable community or authorized custom voices rather
than assuming default voice IDs are permanent.

## Comparison

| Provider | Best fit here | Main strengths | Main cautions | Published pricing observed |
| --- | --- | --- | --- | --- |
| ElevenLabs Eleven v3 | Leading primary engine | Natural multi-speaker dialogue, up to ten voices per dialogue request, 70+ languages, strong emotional range, voice design/library | Dialogue requests are most reliable at 2,000 characters or less; use stable licensed voices rather than expiring defaults | Multilingual v2/v3 is $0.10 per 1,000 characters; paid plan tiers add included capacity |
| Hume Octave 2 | Emotional/acting finalist | Per-utterance delivery descriptions, context continuation, voice design/cloning, word and phoneme timestamps | Octave 2 is preview; official language coverage is narrower than this corpus | Creator $14/month for 140k characters; Pro $70 for 1M; Scale $200 for 3.3M, plus overages |
| Google Gemini 3.1 Flash TTS Preview | Controllable podcast finalist | Exact text recitation, natural-language direction for style/accent/pace/tone, podcast focus, batch API | Preview; only two speakers per request, so three-host turns need separate or paired calls | $1 per million text-input tokens and $20 per million audio-output tokens; batch is half those rates |
| Cartesia Sonic 3.5 | Multilingual fallback and benchmark | Stable pin-able snapshot, 42 languages covering this corpus, expressive conversational speech, pronunciation dictionaries | Sonic 3.5 temporarily lacks the speed/volume controls present in Sonic 3 | Pro $5/month for about 133 minutes; Startup $49 for about 1,667; Scale $299 for about 10,667 |

Pricing comparisons are not perfectly equivalent: vendors meter characters,
audio tokens, credits, or included minutes differently. The casting bakeoff
should record the actual billed cost of the same script.

## OpenAI assessment

OpenAI remains useful as a benchmark, but is not a finalist for this pilot.
The current model catalog marks `gpt-4o-mini-tts` as deprecated; `tts-1-hd` is
an older quality-optimized TTS model; and `gpt-audio-1.5` is aimed more broadly
at audio interaction than deterministic, line-by-line podcast rendering.

## Audition design

Use one source-grounded script containing:

- all three hosts, including a short interruption and fast handoff
- warm banter that does not make fun of a source author
- a concise explanation of crawl timestamps and missing web context
- a restrained emotional passage with a deliberate pause
- names and short fragments in German, Spanish, French, Italian, Dutch,
  Norwegian, Portuguese, and Swedish
- at least one correction or pronunciation dictionary entry

Score each blind sample from 1–5 for naturalness, character distinction,
emotional restraint, pronunciation, multilingual consistency, listening
fatigue, continuity between separately rendered turns, reproducibility,
commercial rights, latency, and measured cost.

## Official sources

- [ElevenLabs models](https://elevenlabs.io/docs/overview/models)
- [ElevenLabs text-to-dialogue API](https://elevenlabs.io/docs/api-reference/text-to-dialogue/convert/)
- [ElevenLabs API pricing](https://elevenlabs.io/pricing/api)
- [ElevenLabs Voice Library](https://elevenlabs.io/docs/eleven-creative/voices/voice-library)
- [ElevenLabs shared voice search](https://elevenlabs.io/docs/api-reference/voices/voice-library/get-shared)
- [ElevenLabs voice overview](https://elevenlabs.io/docs/overview/capabilities/voices)
- [Hume text-to-speech overview](https://dev.hume.ai/docs/text-to-speech-tts/overview)
- [Hume file synthesis API](https://dev.hume.ai/reference/text-to-speech-tts/synthesize-file)
- [Hume pricing](https://www.hume.ai/pricing)
- [Google Gemini speech generation](https://ai.google.dev/gemini-api/docs/speech-generation)
- [Gemini 3.1 Flash TTS Preview](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-tts-preview)
- [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [Cartesia Sonic models](https://docs.cartesia.ai/build-with-cartesia/tts-models/latest)
- [Cartesia custom pronunciations](https://docs.cartesia.ai/build-with-cartesia/capability-guides/custom-pronunciations)
- [Cartesia pricing](https://www.cartesia.ai/pricing)
- [OpenAI model catalog](https://developers.openai.com/api/docs/models/all)
- [OpenAI TTS-1 HD](https://developers.openai.com/api/docs/models/tts-1-hd)
- [OpenAI GPT Audio 1.5](https://developers.openai.com/api/docs/models/gpt-audio-1.5)
