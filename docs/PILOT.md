# Pilot prerequisites

The archive pipeline can run without external services. Before the pilot, the
following decisions and credentials are needed.

## 1. Analysis and script model

Selected: Capriole Fable 5 (`anthropic/claude-fable-5`) for both story analysis
and script generation. The adapter reads `CAPRIOLE_API_KEY` from the process
environment and caches model outputs by story content and prompt version.

The model must continue to demonstrate:

- reliable structured JSON
- long multilingual evidence
- exact quote discipline
- nuanced translation
- source-grounded multi-speaker writing

Analysis and script prompts, model versions, and cached outputs remain
separate even though they use the same service.

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

The researched shortlist and recommended bakeoff are recorded in
[SPEECH_PROVIDERS.md](SPEECH_PROVIDERS.md).

The first 91 completed story cards are the official budget-limited pilot.
Its three-part editorial structure and TTS budget are recorded in
[PILOT_WAVE_1.md](PILOT_WAVE_1.md).

## 3. Editorial choices

Confirmed:

- primary spoken language: English
- pilot crawl month: December 2013
- frozen pilot cohort: 91 analyzed English-language stories
- complete December backlog: 421 stories, with 330 deferred
- coverage policy: use all eligible stories, at different depths
- host format: three disclosed synthetic hosts
- AI budget preference: premium

Still confirm before final audio generation:

- public series title (the current title is a working title)
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
