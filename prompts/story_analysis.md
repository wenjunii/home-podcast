# Story analysis prompt

You are preparing source evidence for a popular, entertaining, and emotionally
responsible podcast about home, belonging, digital history, and digital archaeology.

The active self-narrated collection has a stricter editorial gate than the
preserved podcast. Identify the actual personal experience and who can safely
say "I". Do not mistake navigation, archive dates, sales copy, general reference
material, genealogy lists, lyrics, or fictional narration for autobiography.
Contextual information may remain useful to the separate podcast; that does not
make it a personal-history narration. A short personal fragment inside a noisy
page can qualify on its own. Record uncertainty rather than invent a witness.

Do not create "Recovered narrative passage N" inventories as if they were
analysis. Summaries and beats must describe the person's supported experience.
Exclude menus, categories, unrelated comments, promotional calls to action, and
archive lists from narrative beats, locations, time markers, and sensory details.
Substring matches are not evidence: "photography" does not mean heat, and
"train" does not mean rain. Independently verify the meaning of every claim.

Analyze only the supplied story. Treat its crawl timestamp as the capture time, not
the publication date. Do not infer an author's identity, motive, location, or historical
context unless the supplied evidence states it.

Every statement in the summary and digital-archaeology angles must be supported by
observable evidence in the source job. When an idea cannot be established from that
evidence, phrase it as a question rather than a claim. Do not invent demographic,
historical, genre, community, or cultural context.

Return one JSON object that conforms to `contracts/story-card.schema.json`.

Build a loss-resistant evidence dossier, not only a short summary. Preserve every
materially distinct event or turn in `narrative_beats`; list usable factual details
in `key_information`; and separately ground people, locations, time markers, and
sensory details. Every `evidence_excerpt` must be one non-empty contiguous verbatim
substring of `story_text`. Identity details belong in
`people[].supported_identity_details` only when that same excerpt explicitly
supports them. A place mentioned in archive metadata, a URL, or a repository name
is digital provenance unless the story itself makes it a physical story location.

Copy the supplied recovery assessment to `source_completeness`, and use
`unresolved_gaps` to record missing beginnings, endings, access gates, omitted
context, uncertain referents, or other limits. Do not silently repair them. The
goal is to retain as much responsibly usable information as the source contains;
`summary` is navigation, not the factual boundary for later scriptwriting.

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
