# Pilot prerequisites

The archive pipeline can run without external services. Before the pilot, the
following decisions and credentials are needed.

## 1. Analysis and script model

Selected: Capriole Fable 5 (`anthropic/claude-fable-5`) for story analysis and
Claude Opus 4.6 (`anthropic/claude-opus-4-6`) for script generation and
conversation polish. The adapter reads `CAPRIOLE_API_KEY` from the process
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

The pilot casting test is complete. Future episodes draw an accent-diverse,
role-matched lineup from `config/voice_roster.json` and freeze the result before
script and audio production. The pilot cast itself remains frozen. Nine
additional international English candidates are in same-script listening
review and are not yet eligible for rotation. Casting checks should include:

- light banter
- an emotional but restrained passage
- a digital-archaeology explanation
- multilingual names and original-language excerpts
- a shift from humor to seriousness
- short interruptions

Score naturalness, host distinctness, emotional restraint, pronunciation,
cross-language consistency, long-form fatigue, output stability, commercial
rights, and per-episode cost.

Use licensed stock voices or explicitly authorized custom voices.
Do not clone an identifiable real person without permission.
An accent is ordinary cast metadata, not a performance joke. Do not prompt a
voice to imitate a nationality, and do not use accent as shorthand for a
character's knowledge, personality, or social role.

The researched shortlist and recommended bakeoff are recorded in
[SPEECH_PROVIDERS.md](SPEECH_PROVIDERS.md).

The 91 completed story cards form the analyzed production pool. The official
budget-limited pilot selects its strongest single theme: 27 stories about
Exile, Return, and Nostalgia. Its episode structure and TTS budget are recorded
in [PILOT_EPISODE.md](PILOT_EPISODE.md).

## 3. Editorial choices

Confirmed:

- primary spoken language: English
- pilot crawl month: December 2013
- analyzed production pool: 91 English-language stories
- frozen pilot cohort: 27 stories in Exile, Return, and Nostalgia
- complete December corpus: 421 stories
- deferred after the pilot: 64 analyzed stories and 330 unanalyzed stories
- pilot release: one approximately 30-minute themed sub-episode
- coverage policy: use all 27 selected stories, at different depths
- host format: three natural, friend-like hosts with a frozen rotating cast
- pilot cast: Maya/Bella, Theo/Roger, and Lina/Lily
- pilot performance style: Creative+
- audio deliverables: synchronized voices-only and non-human-only tracks
- non-human coverage: continuous base bed with long thematic handoffs
- future cast policy: rotating people and verified accents, frozen per episode
- speech subscription: ElevenLabs Creator, with 192 kbps production output
- on-air host-generation disclosure: omitted
- AI budget preference: premium
- completed speech render: 128 turns, 17 cached Creative+ chunks, 30:44.72
- completed speech cost: 14,921 provider-reported credits
- completed outputs: voices-only, soundscape-only, combined review mix, Markdown, WebVTT, and SRT

Still confirm before publication:

- public series title (the current title is a working title)
- final listening approval of the rendered voices and 13-cue soundscape
- any licensed replacements for generated effect candidates
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
- no on-air dialogue discusses host-generation technology
- no source is presented as an interview or simulated author
- the rendered audio is listenable without visual context
- loudness, clipping, captions, and source maps pass QA
