# Pilot: 91 analyzed stories

Prepared July 25, 2026 from the story cards that completed before the Capriole
traffic block. The log counter reached 92 because the next request was
attempted, but the frozen usable cohort contains 91 validated story cards.

This is the official budget-limited pilot. The complete 421-story December
snapshot remains preserved as a future backlog, but the remaining 330 stories
will not incur analysis, script, or speech-generation costs for this pilot.

## Corpus profile

- 91 stories
- 91 English-language stories
- 191,712 source-story characters
- all 91 currently marked eligible
- one anchor, 34 featured, 38 supporting, 15 fragments, and 3 contextual uses

The all-English composition reflects which API calls finished first. It is not
representative of the complete December corpus.

## Proposed single-episode structure

### 2013-12.01 — 91 Fragments of Home

One approximately 55-minute episode with three internal acts:

#### Act 1 — The Homes We Leave

34 stories about exile, nostalgia, lost places, migration, borders, and
displacement.

#### Act 2 — What We Carry Forward

27 stories about family, inheritance, objects, food, rituals, memory, archives,
language, and cultural belonging.

#### Act 3 — How We Make Home

30 stories about identity, physical places, chosen community, housing
precarity, and the internet as home.

Every story is assigned exactly once. Individual stories can receive anchor,
featured, supporting, fragment, or contextual treatment so coverage does not
make the conversation sound like a list.

## Runtime and text assumptions

Target the complete episode at about 55 minutes:

- final program audio: about 55 minutes
- final spoken script: about 8,250 words at 150 words per minute
- estimated final TTS text: about 55,000 characters
- production allowance: 1.5 generations per retained line
- estimated billed generation: about 82,500 characters or 82.5 audio minutes

The regeneration allowance covers pronunciation fixes, delivery retakes, and
limited alternate takes. Music, silence, and already-rendered ambience do not
need TTS.

## Estimated TTS cost

| Provider | Nominal pilot cost with 1.5x generation | Capacity note |
| --- | ---: | --- |
| ElevenLabs Eleven v3 | About $8.25 pay as you go | $0.10 per 1,000 characters. The current Creator offer is $11 for the first month and includes 220,000 Multilingual v2/v3 characters; regular Creator is $22/month. |
| Hume Octave 2 | $7 first month; $14 thereafter | Creator includes 140,000 characters, comfortably above the estimated 82,500. |
| Google Gemini 3.1 Flash TTS Preview | About $2.50 standard, or $1.25 batch | Estimate includes about 123,750 audio tokens at 25 tokens/second plus a few cents of text input. Preview pricing and behavior may change. |
| Cartesia Sonic 3.5 | $5 Pro plan | Pro includes about 133 generated minutes, leaving roughly 50 minutes beyond the 1.5x estimate. |

These are API-generation estimates, not total production budgets. They exclude
the script-writing LLM, music licensing, human review, hosting, and taxes.
Actual TTS billing should be recalculated from the validated script before
generation.

## Recommended spend sequence

1. Write one source-grounded 3–5 minute audition scene.
2. Render it once with all four providers.
3. Blind-score voices and delivery.
4. Select one provider and stable voice IDs.
5. Generate the complete episode segment by segment.

Do not render the full episode with all four providers. The provider audition
should be small; only the selected engine should receive the full script.

## Pricing sources

- [ElevenLabs API pricing](https://elevenlabs.io/pricing/api)
- [Hume pricing](https://www.hume.ai/pricing)
- [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [Cartesia pricing](https://www.cartesia.ai/pricing)
