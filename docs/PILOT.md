# Pilot prerequisites

The archive pipeline can run without external services. Before the pilot, the
following decisions and credentials are needed.

## 1. Analysis and script model

Choose a model capable of:

- reliable structured JSON
- long multilingual evidence
- exact quote discipline
- nuanced translation
- source-grounded multi-speaker writing

The analysis model and script model may be the same service, but their prompts,
model versions, and cached outputs remain separate.

## 2. Speech casting

Run a blind casting test before assigning `voice_id` values. Use the same
three-to-five-minute audition script for every candidate speech engine. It
should contain:

- light banter
- an emotional but restrained passage
- a digital-archaeology explanation
- multilingual names and original-language excerpts
- a shift from humor to seriousness
- short interruptions

Score naturalness, host distinctness, emotional restraint, pronunciation,
cross-language consistency, long-form fatigue, output stability, commercial
rights, and per-episode cost.

Use licensed stock synthetic voices or explicitly authorized custom voices.
Do not clone an identifiable real person without permission.

## 3. Editorial choices

Confirm before generating a pilot:

- public series title (the current title is a working title)
- primary spoken language
- desired pilot crawl month
- approximate duration
- whether music and ambience are used
- publication/licensing policy for source excerpts
- sensitivity and translation review standard

## 4. Credentials

Provider credentials must be supplied through environment variables or the
system credential store. They must not be placed in `podcast.json`, the show
bible, job JSONL, episode manifests, or source control.

## 5. Pilot acceptance gates

The pilot is ready to publish only when:

- every selected story has a traceable use
- quotations match archived evidence
- translations and pronunciations are reviewed
- synthetic-host disclosure is present
- no source is presented as an interview or simulated author
- the rendered audio is listenable without visual context
- loudness, clipping, captions, and source maps pass QA
