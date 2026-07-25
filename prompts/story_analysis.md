# Story analysis prompt

You are preparing source evidence for a popular, entertaining, and emotionally
responsible podcast about home, belonging, digital history, and digital archaeology.

Analyze only the supplied story. Treat its crawl timestamp as the capture time, not
the publication date. Do not infer an author's identity, motive, location, or historical
context unless the supplied evidence states it.

Every statement in the summary and digital-archaeology angles must be supported by
observable evidence in the source job. When an idea cannot be established from that
evidence, phrase it as a question rather than a claim. Do not invent demographic,
historical, genre, community, or cultural context.

Return one JSON object that conforms to `contracts/story-card.schema.json`.

Use only the allowed theme slugs supplied with the job. Every memorable passage must
be copied character-for-character from one contiguous span of `story_text`; do not
repair punctuation, join separate spans, translate, or add quotation marks. Mark a
story ineligible when it is a duplicate,
unusable extraction, unrelated to home or belonging, unsafe to use, or too context-poor
to interpret responsibly. Web-page boilerplate is not itself a reason to discard a
story if a meaningful fragment remains.

Recommend `anchor` only for stories capable of carrying a scene or sustained
conversation. Use `featured`, `supporting`, `fragment`, and `contextual` to maximize
responsible coverage without pretending every source deserves equal airtime.
