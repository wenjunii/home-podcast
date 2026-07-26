# Codex-native semantic production

Story analysis, episode scripts, and visual prompts can be produced directly
inside a Codex task. This is the project default. Capriole remains available
for explicitly requested unattended or API-driven batches.

## What to ask

These short requests are sufficient:

- `Analyze the newly extracted stories for December 2013.`
- `Plan the next themes and sub-episodes from the analyzed stories.`
- `Build episode 2013-12.02 from its locked evidence.`
- `Revise the script to make the hosts more natural and emotionally varied.`
- `Generate the visual prompts for episode 2013-12.02.`

Codex should inspect the repository state, determine the incremental scope,
produce the requested artifacts, run deterministic importers and validators,
and report rejected or pending items.

## Division of responsibility

| Work | Default |
|---|---|
| Ingest, IDs, hashes, crawl dates, manifests | Local deterministic code |
| Story analysis and theme cards | Codex task + `import-cards` |
| Episode planning | Local planner, with Codex editorial review |
| Script generation and polishing | Codex task + `validate-script` |
| Captions and sequencer timing | Local deterministic code |
| SDXL prompt writing | Codex task + `import-visual-prompts` |
| Speech and sound generation | ElevenLabs, only when requested |
| Live image generation | StreamDiffusionTD |
| Unattended text-generation fallback | Capriole, only when requested |

## Incremental behavior

`ingest` compares stable story IDs and content hashes. `export-analysis`
exports only stories without a current card unless explicitly told to include
existing work. This means another extraction can add stories from any crawl
month without forcing a full rerun.

Locked episode manifests are never silently expanded. New stories found after
an episode is published belong in a supplement or a later episode.

## Validation gates

Codex-authored artifacts do not bypass the production contracts:

- `import-cards` rejects stale content hashes and malformed story cards.
- `validate-script` checks selected-story coverage, citations, speakers, and
  exact quotations.
- `import-visual-prompts` verifies story evidence and counts both local SDXL
  tokenizers before applying prompts.
- `validate-visuals` checks complete timing coverage and prompt structure.

No text-generation API credential is required for these Codex-native passes.
They use the active Codex task’s plan allowance instead of Capriole billing.
ElevenLabs and StreamDiffusionTD remain separate external systems.

## External API fallback

The configured Capriole commands remain useful for unattended automation. They
must start with a dry run and an explicit paid-call ceiling. Credentials stay
in the process environment and must never be stored in the repository.

The authoritative agent-facing procedure is in [`AGENTS.md`](../AGENTS.md).
