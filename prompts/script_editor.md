# Episode trim prompt

Create a deletion-only editorial plan for the supplied podcast script.

The goal is a tighter, more popular 30-minute episode without losing its
knowledge, humor, emotional resonance, source coverage, or three-host rhythm.

Rules:

- Return raw JSON only: `{"delete_segment_ids": [...], "editorial_note": "..."}`.
- Delete complete turns only. Do not rewrite, merge, or add dialogue.
- Reach the supplied target word range.
- Preserve every story: each evidence story ID must remain cited by at least one
  surviving segment.
- Never delete a `quote` segment.
- Preserve the cold open, the crawl-month explanation, the three-movement arc,
  emotional breathing room after trauma, and the final archive-limit reflection.
- Prefer cutting repetition, over-explanation, generic reactions, duplicated
  setup, and jokes that delay the story.
- Preserve distinct host personalities and natural conversational handoffs.
- Do not delete so many turns that any generation section disappears.
