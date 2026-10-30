# Recovered Homes — Codex production instructions

These instructions apply to the complete repository.

## Default operating mode

- Perform story analysis, theme development, episode planning, scriptwriting,
  script polishing, and SDXL prompt writing directly in the active Codex task.
- Use GPT-6.1 Sol (`gpt-6.1-sol`) with Extra High reasoning (`xhigh`) for
  story analysis, first-person writing (initial adaptations and revisions),
  and visual prompt writing in this Codex conversation, as requested by the
  user. This supersedes the earlier GPT-6 Astra Max and GPT-5.6 Sol Extra High
  preferences for those tasks.
- Select the requested model and reasoning level in the Codex conversation
  controls. Repository instructions do not switch the running model; do not
  claim that this preference proves which model produced an artifact, relabel
  existing artifacts, or invoke a separate paid API to satisfy it.
- Do not call Capriole or another paid text-generation API unless the user
  explicitly requests the external API for that run. A previous API key or an
  external-provider configuration is not standing authorization for new calls.
- Before any paid generation, run the provider command in dry-run mode, report
  the exact pending-call ceiling, and keep the provider runner resumable.
- Keep the Capriole adapters and `podcast.json` provider configuration as an
  optional automation fallback. Do not remove or silently replace them.
- ElevenLabs and StreamDiffusionTD remain external media-generation systems.
  Do not start their servers or make paid calls unless the user requests that
  production step.
- Never write credentials into source, configuration, jobs, caches, logs,
  transcripts, `.toe` files, shell scripts, or documentation.

## Invariants

- Read story sources only from `stories_*.md`; ignore `matches*` files and the
  compressed JSONL export.
- Treat the Common Crawl timestamp as capture time, not writing or publication
  time.
- Work incrementally from stable story IDs and content hashes. Never reanalyze
  unchanged current story cards merely to rebuild a later artifact.
- A locked or published episode manifest is immutable. Late discoveries belong
  in a supplement or later episode.
- Use `work/` for rebuildable jobs and intermediate Codex results. Use
  `episodes/` for reviewed episode state and publishable artifacts.
- AI may interpret and compose, but deterministic code owns provenance, IDs,
  hashes, exact-quotation checks, story coverage, timing, SDXL token limits,
  caching, and final validation.
- Locations and identities require evidence from the current job. Location
  never implies race, ethnicity, nationality, gender, age, or belonging.
- An archive, URL, filename, OCR repository, or genealogy website is digital
  provenance, not a physical story location.
- Preserve the show’s on-air fiction: hosts sound like ordinary friends and do
  not discuss synthesis, models, prompts, providers, or being artificial.

## Active self-narrated storytelling path

The current production direction is one conversational performed history per
eligible source story. Keep every podcast config, manifest, script, audio,
soundscape, visual, and TouchDesigner artifact intact for possible later use.
Self-narrated work uses `storytelling.real-december.json` and writes only under
`narrations/real-december`, `work/storytelling-real-december`, and
`audio/storytelling-real-december`.

- Prefer `first_person_preserved` whenever the source establishes a narrator
  who can safely say “I” or “we,” including incomplete sources.
- Use `attributed_first_person` for explicitly attributed testimony.
- The storytelling collection is first-person only. Hold a story when the
  recovered source cannot safely establish who may say “I.” Never invent a
  person, combine multiple identities, or convert unsupported facts into
  first-person memory.
- Retell rather than read: preserve the central experience, important context,
  identity, location, causal sequence and unresolved ending while using natural
  spoken phrasing, contractions, varied rhythm and restrained performance.
- Treat the selected voice as an artistic performer, not the original writer
  or witness. Voice gender, accent, age, and other demographic characteristics
  become constraints only with exact source evidence; otherwise they are
  documented artistic choices.
- Keep laughter, breaths, sighs, hesitations, and similar direction in delivery
  fields rather than transcript text.
- New story narrations have a maximum finished runtime of five minutes
  (300 seconds), including breaths, pauses and tail silence. Aim for roughly
  450–550 English words or fewer to leave room for expression; this is planning
  guidance, not an exact conversion. Measure completed audio before acceptance.
  The user's current choice is ONE condensed version per story, never parts.
  Condense secondary details and repetition editorially, document narrative
  omissions as `duration_condensation`, and preserve the complete source and
  previous full adaptation. Never cut off a recording, accelerate speech or
  invent closure. Existing recordings and the podcast plan stay intact.
- First-person pronouns alone do not establish a personal history. Separate
  lived experience from general information, advertisements, service pitches,
  archive menus, genealogy lists, lyrics, and fictional speakers. Keep genuine
  personal fragments; hold unsupported witnesses instead of inventing them.
- Keep source commentary (including "the source says"), capture/publication
  metadata, archive month lists, and recovery-gap explanations out of speech.
  Preserve source gaps and attribution in metadata; retain dates only when they
  materially belong to the person's experience.
- Structural validation is not editorial approval. Before personal-story
  audio or visual production, require a current `personal-story-review.json`
  with exact personal-experience evidence, corrected analysis and locations,
  approved section IDs, and hashes of the adaptation and frozen source job.
  Never bulk-approve the review queue or count mechanical cards as analysis.
- Run `python -m scripts.audit_personal_story_content --config
  storytelling.real-december.json` after editorial changes. The pending review
  queue remains separate from the missing/invalid adaptation export queue.

When the user asks to build or continue the self-narrated histories:

1. Refresh the deterministic plan and pending jobs as needed:

   ```powershell
   py -3.10 -m home_podcast `
     --config .\storytelling.real-december.json `
     plan-storytelling --month 2013-12
   py -3.10 -m home_podcast `
     --config .\storytelling.real-december.json `
     export-storytelling `
     --plan .\work\storytelling-real-december\planning\2013-12-storytelling-plan.json
   ```

2. Read `prompts/storytelling_writer.md`,
   `contracts/storytelling-script.schema.json`,
   `config/storytelling_bible.json`, and every selected job. Write one JSON
   object per line to
   `work/storytelling-real-december/adaptations/2013-12-results.jsonl`.
3. Account for every required evidence excerpt as support or a documented
   editorial omission, disclose required source gaps in metadata, and preserve
   exact direct quotations. For the requested single short edition, retain the
   central personal arc and document secondary details omitted for duration.
4. Import through the local deterministic gate:

   ```powershell
   py -3.10 -m home_podcast `
     --config .\storytelling.real-december.json `
     import-storytelling `
     --input .\work\storytelling-real-december\adaptations\2013-12-results.jsonl `
     --jobs .\work\storytelling-real-december\adaptations\2013-12-jobs.jsonl
   ```

5. Re-export the plan and rerun the personal-story content audit. Completion
   requires both structural import and current evidence-backed editorial
   approval for the requested scope (or an explicit, reported hold). Zero
   missing adaptations does not clear the separate editorial-review queue.
   Do not call a text-generation provider; author the adaptations in the active
   Codex task.

## Local live storytelling variations

- `3080_safe` is the default profile. It uses canonical Codex adaptations,
  cached ElevenLabs speech, and canonical visual prompts; it must not import or
  load Ollama or Qwen3-TTS.
- `5090_live` may use local Ollama `gemma4:12b` and local Qwen3-TTS only after
  the user explicitly starts the worker and enables the Show Control switch.
- The local model may vary only a reviewed canonical adaptation. Never send
  unvalidated model text directly to TTS or StreamDiffusionTD.
- One casting card is stable for a complete rendition. Source-explicit traits
  are locked; unspecified voice, accent, age, gender presentation, personality,
  and appearance are documented artistic casting rather than source identity.
- Accent, location, language, and name never imply physical appearance, race,
  ethnicity, nationality, gender, class, or religion.
- Use independent casting, narration, speech, visual-prompt, and image seeds.
  Promote a rendition only after all requested artifacts validate and exist;
  otherwise keep the canonical assets or last-known-good bundle.
- TouchDesigner consumes the file protocol under
  `work/storytelling-real-december/runtime`. Apply new bundles only at story or
  loop boundaries, never by interrupting current speech.

## When the user says “analyze the new stories”

1. Run:

   ```powershell
   python -m home_podcast ingest
   python -m home_podcast status
   ```

2. Export only uncached current records. Restrict by month or cohort when the
   user names one:

   ```powershell
   python -m home_podcast export-analysis `
     --month YYYY-MM `
     --output .\work\codex\analysis\YYYY-MM-jobs.jsonl
   ```

3. Read `prompts/story_analysis.md`, `config/themes.json`, and every exported
   job. Produce one JSON object per line at
   `work/codex/analysis/YYYY-MM-cards.jsonl`, preserving each `story_id` and
   `content_hash` exactly.
4. Use only verbatim source substrings for `memorable_passages`. Do not
   translate or silently repair quotations. Summaries may be in English while
   the original evidence stays unchanged.
5. Import through the existing deterministic gate:

   ```powershell
   python -m home_podcast import-cards `
     .\work\codex\analysis\YYYY-MM-cards.jsonl `
     --analyzer codex-interactive `
     --analyzer-version story-analysis-v1
   ```

6. Re-export the same scope. Completion means no unchanged job remains pending;
   changed or invalid cards must remain visible for correction.

Do not run `python -m home_podcast analyze` in the default Codex-native mode;
that command invokes the configured external LLM.

## When the user says “build the next episode script”

1. Confirm the episode uses a locked manifest and frozen cast. Prepare its
   evidence packet when needed:

   ```powershell
   python -m home_podcast prepare-script `
     --manifest .\episodes\<episode>\manifest.json `
     --episode <episode>
   ```

2. Read the evidence packet, `episodes/<episode>/outline.json`,
   `prompts/script_writer.md`, `contracts/script.schema.json`,
   `config/show_bible.json`, and the frozen cast.
3. Write or revise `episodes/<episode>/script.json` directly. The conversation
   must be curious, funny where natural, emotionally resonant, accessible to a
   general audience, and built from friendly exchanges rather than alternating
   essays.
4. Use every selected story traceably. Keep direct quotations exact. Never
   invent a source, identity, location, pronunciation, or interview.
5. Store laughter, sighs, breaths, and similar performance direction in the
   existing TTS-only delivery fields, not as transcript text.
6. Validate before treating the script as complete:

   ```powershell
   python -m home_podcast validate-script `
     --script .\episodes\<episode>\script.json `
     --evidence .\work\scripts\<episode>-evidence.json
   ```

Do not run `generate-script` or `polish-script` in default Codex-native mode;
those commands invoke the configured external LLM. Keep them as opt-in
automation fallbacks.

## When the user says “generate the visual prompts”

1. Prepare or expand the deterministic visual plan first. Respect the current
   declared scene minimum, speech/story boundaries, long-image preference, and
   crossfade policy.
   The active 136-story December revision uses a five-second minimum, as
   requested on 2026-10-30. Preserve all other scopes and legacy 15-second editions. Each included story may have
   a source-grounded opening-context image at its exact start; later actions,
   places, and reveals still require their measured speech gates.
2. Read `prompts/visual_prompt_writer.md`, the visual job JSONL, the visual
   scene contract, and any `complementary_prompt_context`.
3. Write one raw result object per line to:

   ```text
   work/codex/visuals/<episode>-results.jsonl
   ```

4. Each result must:

   - preserve the exact job `scene_id`;
   - provide evidence-grounded location and identity claims;
   - cite contiguous excerpts from that job’s `source_evidence`;
   - avoid identities not explicitly supported;
   - avoid repeating the retained parent composition when complementary
     context exists;
   - contain one to three narrative candidates, from which the importer keeps
     the longest valid 68–75-token SDXL prompt;
   - keep “4K photography” as an aesthetic direction rather than a resolution
     claim.

5. Import through the no-network validator:

   ```powershell
   python -m home_podcast import-visual-prompts `
     --input .\work\codex\visuals\<episode>-results.jsonl `
     --jobs .\work\visuals\<episode>-prompt-jobs.jsonl `
     --visuals .\episodes\<episode>\visuals\<episode>-visual-scenes.json `
     --model-label codex-interactive
   ```

6. Run `validate-visuals`. Generated prompts remain pending human editorial
   approval even after evidence and tokenizer checks pass.

Do not run `generate-visual-prompts --execute` in default Codex-native mode;
that path invokes the configured external LLM.

## Verification and handoff

- Run focused tests while editing and `python -m unittest discover -s tests`
  before final handoff when project code or contracts changed.
- Run `git diff --check`.
- Scan project text for credential-shaped strings without printing secret
  contents.
- Report the scope processed, counts imported/generated, pending or rejected
  items, validator status, and whether any network or paid calls occurred.
- Do not commit, push, create a pull request, publish audio, or overwrite a
  `.toe` project unless the user explicitly requests that action.
- TouchDesigner reads the external scene JSON. After visual changes, instruct
  the user to reopen the latest local `.toe` or reload the controller; do not
  start both StreamDiffusionTD model servers.
