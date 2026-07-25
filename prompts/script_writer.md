# Episode script prompt

Write an entertaining multi-host podcast script from the supplied evidence packet.
The goal is knowledge, fun, inspiration, and emotional resonance for a general
audience. The tone is curious and lively rather than solemn or academic.

Follow the supplied show bible and `contracts/script.schema.json`.

Requirements:

- Use every evidence story and cite its story ID in at least one segment.
- Let anchor stories carry scenes; weave supporting stories into choruses, contrasts,
  callbacks, and short fragments.
- Make all factual and interpretive claims traceable to the cited source IDs.
- Copy exact quotations verbatim. Never invent dialogue for an original author.
- Make uncertainty audible where the archive has gaps.
- Explain once that the archive volume is a crawl month, not a publication month.
- Give the three hosts different conversational functions.
- Make the current episode cast sound like friends who know one another: use
  follow-up questions, callbacks, gentle disagreement, interruptions, surprise,
  and shared discovery.
- Prefer short, responsive turns over alternating monologues or narrated lists.
- Never discuss or identify the technology used to create the hosts or voices.
- Add sparse, context-appropriate vocal reactions in `delivery.audio_tags`, such
  as `laughs softly`, `sighs`, `exhales`, or `hesitates`. Do not overuse them.
- Use humor around host behavior, odd metadata, and web artifacts; never make a
  vulnerable person or traumatic experience the punchline.
- Avoid canned banter and repetitive agreement.
- Do not place a joke immediately after sensitive or traumatic material.
- End with both an emotional echo and an honest statement about what the archive
  cannot tell us.
