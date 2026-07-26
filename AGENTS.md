# Recovered Homes — Codex production instructions

These instructions apply to the complete repository.

## Default operating mode

- Perform story analysis, theme development, episode planning, scriptwriting,
  script polishing, and SDXL prompt writing directly in the active Codex task.
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
   15-second minimum, speech/story boundaries, long-image preference, and
   crossfade policy.
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
