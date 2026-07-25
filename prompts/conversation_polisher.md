# Conversation polish prompt

Polish one section of a source-grounded podcast script so the three hosts sound
like intelligent friends discovering the material together.

The result should feel interesting, curious, inspiring, and emotionally moving
without becoming solemn, theatrical, or overproduced.

Rules:

- Return one raw JSON object with only a `segments` array.
- Return every supplied segment exactly once and in the same order.
- Preserve every `segment_id`, `speaker`, `kind`, `source_story_ids`,
  `pronunciation`, and `pause_after_ms`.
- Preserve every `quote` segment's text exactly.
- For other turns, retain the complete factual meaning and named details. This
  is a style polish, not a fact-adding or fact-removing rewrite.
- Keep the section within ten percent of its original word count.
- Make turns respond to each other through genuine questions, callbacks,
  surprise, gentle disagreement, unfinished thoughts, and changes of emotional
  energy. Do not turn every line into banter.
- The hosts know one another and speak naturally. Avoid alternating mini-essays,
  canned agreement, repeated summaries, and phrases like "that's fascinating."
- Never discuss or identify how the hosts or voices are produced.
- Use humor only around the hosts, odd metadata, or web artifacts. Never laugh
  at vulnerable people, grief, displacement, illness, or trauma.
- Use `delivery.tone` for performance direction when helpful.
- Add `delivery.audio_tags` sparingly for audible reactions such as
  `laughs softly`, `chuckles`, `sighs`, `exhales`, or `hesitates`. Most turns
  should have no reaction tag, and sensitive passages should remain restrained.
- Do not place bracketed performance directions inside `text`.
