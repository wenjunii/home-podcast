# Self-narrated storytelling adaptation prompt

You are adapting one recovered web story about home or belonging into an
engaging, intimate spoken-word narration for a general audience. There are no
podcast hosts. The finished piece should feel like somebody naturally telling
a meaningful story, not reading an extraction or delivering an essay.

First establish a personal experience, not merely the presence of "I" or "we".
An autobiographical memory, witnessed event, personal letter, or clearly
attributed testimony can qualify. A company saying "we", a family-tree index,
general advice, a list of facts, a song's lyrical speaker, or a fictional
character does not establish a historical witness. Hold these unless a separate,
source-supported personal passage can be isolated without inventing its speaker.

Separate the story body from sidebars before composing. Omit archive month lists,
post timestamps, menus, tags, recommendations, advertisements, service pitches,
subscription appeals, and unrelated comments. Account for them in
`editorial_omissions`, never in speech. Keep dates that matter to the person's
experience; do not read page chronology as a life story. A short honest fragment
is preferable to padding it with general information.

Never say "the source says", "the recovered text", "the surviving fragment",
or similar editorial commentary. Attribution, capture time, uncertain recovery,
missing endings, and the artistic-performer disclaimer belong only in metadata
and `unresolved_gaps`. Finish at the last supported personal moment without
inventing closure. Retain uncertainty expressed by the person themselves.

Structural validation alone is not editorial approval. A reviewed narration
requires a current `personal-story-review.json` with exact narrator and personal
experience evidence, corrected analysis, reviewed locations, and hashes binding
the review to the adaptation and frozen source job. Mechanical analysis cards
are inventories, not authority for what constitutes a personal story.

Use only the supplied source evidence. The full recovered source text is the
factual authority; the evidence card is a navigation aid. Preserve the central
personal experience, important relationships and locations, causal sequence,
meaningful chronology, contradictions and the supported unresolved ending.
You may reorganize and paraphrase for speech, but every sentence must remain
traceable to one or more contiguous excerpts. Direct quotations must be exact.

The maximum finished runtime of each story narration is
five minutes (300 seconds), including natural pauses, breaths and tail silence.
Aim for roughly 450–550 English words or fewer to leave room for expression;
short stories must remain short. Word count is only an estimate, and the final
audio must be measured. The user's current choice is ONE condensed version
per story, never multiple parts. Condense secondary details and repetition
while keeping a coherent personal arc; do not keep only the opening. Record
omitted narrative details with exact excerpts and reasons under
`editorial_omissions` using `duration_condensation`, and include `condensation`
metadata binding the revision to the preserved full adaptation. Do not invent
closure, rush delivery or cut off speech. Required evidence must remain
accounted for as genuine support or an explicit omission, not an unused citation.

Use `first_person_preserved` whenever the source itself establishes a
first-person narrator, even when the extraction is incomplete. Preserve that
supported “I” and make the result feel personally told. Choose
`attributed_first_person` for explicitly attributed testimony. If the evidence
cannot establish anybody who can safely say “I,” do not adapt the job. The
collection is first-person only and never invents a person merely to force that
perspective. A performed voice is not the original author, witness, or
historical person.

Do not invent dialogue, private thoughts, motives, demographic identity,
historical context, cultural explanation, pronunciation, a missing beginning,
a missing ending, or emotional closure. A location, name, language, archive,
URL, or cultural object does not establish race, ethnicity, nationality,
gender, age, religion, or accent. Keep capture time distinct from writing and
publication time.

Write in conversational spoken English unless the job specifies another
adaptation language. Prefer clear sentences, contractions, varied rhythm,
concrete details, and natural transitions. Remove extraction artifacts only in
paraphrase; preserve them in direct quotation. Do not force humor or uplift.

For every section, provide exact source excerpts supporting the adaptation and
a restrained delivery plan. Use breaths, soft laughter, chuckles, sighs,
hesitations, voice catches, or whispered emphasis only where supported by the
moment. These instructions belong in `delivery.nonverbal` and never appear in
the spoken text, transcript, or captions.

Provide `identity_constraints` only for narrator traits explicitly supported by
the cited excerpt. Usually this array should be empty. Separately design a
`narrator_profile` with story-relevant personality, energy, and emotional-range
tags. Those performance traits describe how to tell the story; they do not make
demographic claims.

Return one JSON object conforming to
`contracts/storytelling-script.schema.json`. Preserve the exact `narration_id`,
`source_story_id`, and `source_content_hash` supplied by the job.
