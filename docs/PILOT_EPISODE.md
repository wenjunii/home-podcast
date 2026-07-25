# Pilot episode: Exile, Return, and Nostalgia

Prepared July 25, 2026 from the 91 story cards that completed before the
Capriole traffic block.

The series plan still supports multiple themed sub-episodes. The
budget-limited pilot produces only one: the strongest theme in the analyzed
pool. The other analyzed themes remain available for future sub-episodes.

## Corpus profile

- selected theme: Exile, Return, and Nostalgia
- 27 eligible English-language stories
- 66,076 source-story characters
- one anchor, 13 featured, 11 supporting, and 2 fragment uses
- highest anchor score in the analyzed pool: 0.82

This theme was selected because it has the only anchor-rated story, the
largest body of featured material, and a clear emotional arc for a general
audience.

## Proposed episode

### 2013-12.01 — The Homes We Leave Behind

One approximately 30-minute sub-episode with three internal movements:

1. Leaving and distance
2. Returning to a home changed by time and memory
3. What an old web capture preserves—and what it cannot

Every selected story is assigned exactly once. Their depth varies so the
conversation does not sound like a list.

The locked manifest and six-section production outline are in
`episodes/2013-12.01/`. The smaller sections are generation checkpoints within
the three audience-facing movements, not additional sub-episodes.

## Runtime and text assumptions

Target the episode at about 30 minutes:

- final program audio: about 30 minutes
- final spoken script: about 4,500 words at 150 words per minute
- estimated final TTS text: about 30,000 characters
- production allowance: 1.5 generations per retained line
- estimated billed generation: about 45,000 characters or 45 audio minutes

The regeneration allowance covers pronunciation fixes, delivery retakes, and
limited alternate takes. Music, silence, and already-rendered ambience do not
need TTS.

## Current script draft

The first source-validated script was generated with
`anthropic/claude-opus-4-6`:

- 158 speaking turns
- 5,341 spoken words
- 30,141 spoken characters
- approximately 35.6 minutes at 150 words per minute
- all 27 selected stories cited
- all exact quotations verified against source text

This is a complete long first cut. Before speech generation, trim roughly
800–900 words to approach the 30-minute editorial target while preserving
coverage of all 27 stories.

## Estimated TTS cost

| Provider | Nominal pilot cost with 1.5x generation | Capacity note |
| --- | ---: | --- |
| ElevenLabs Eleven v3 | About $4.50 pay as you go | $0.10 per 1,000 characters. The current Creator offer is $11 for the first month and includes ample capacity; regular Creator is $22/month. |
| Hume Octave 2 | $7 first month; $14 thereafter | Creator includes 140,000 characters. The $3 Starter tier covers only about one clean 30-minute pass, with little room for retakes. |
| Google Gemini 3.1 Flash TTS Preview | About $1.37 standard, or $0.69 batch | Estimate includes about 67,500 audio tokens at 25 tokens/second plus a few cents of text input. Preview pricing and behavior may change. |
| Cartesia Sonic 3.5 | $5 Pro plan | Pro includes about 133 generated minutes, leaving ample retake capacity. |

These are API-generation estimates, not total production budgets. They exclude
the script-writing LLM, music licensing, human review, hosting, and taxes.
Actual TTS billing should be recalculated from the validated script before
generation.

## Recommended spend sequence

1. Write one source-grounded 3–5 minute audition scene.
2. Render it once with all four providers.
3. Blind-score voices and delivery.
4. Select one provider and stable voice IDs.
5. Generate the selected themed sub-episode segment by segment.

Do not render the full episode with all four providers. The provider audition
should be small; only the selected engine should receive the full script.

## Pricing sources

- [ElevenLabs API pricing](https://elevenlabs.io/pricing/api)
- [Hume pricing](https://www.hume.ai/pricing)
- [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [Cartesia pricing](https://www.cartesia.ai/pricing)
