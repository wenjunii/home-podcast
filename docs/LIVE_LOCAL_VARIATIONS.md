# Buffered local storytelling variations

The live path creates another performance of an already reviewed first-person
adaptation. It does not replace source analysis, the canonical Codex
adaptation, the initial ElevenLabs render, or human editorial approval.

## Runtime profiles

| Profile | Narration | Speech | Visual prompts | Local model loading |
| --- | --- | --- | --- | --- |
| `3080_safe` | Canonical Codex | Cached reviewed initial render (local Qwen or ElevenLabs fallback) | Canonical Codex | Disabled |
| `5090_live` | Gemma 4 12B variation | Qwen3-TTS | Gemma 4 12B variation | Explicit opt-in |

`config/live_storytelling.json` is hardware policy, not a credential file. The
Ollama adapter rejects every non-loopback host. The Qwen adapter is imported
only when a 5090 speech render actually begins.

## Safety and continuity

Each future rendition receives five independent seeds: casting, narration,
speech, visual prompt, and StreamDiffusion image. A single casting card remains
stable for the complete rendition. A new card may be selected at the next
loop.

- Source-explicit identity traits are locked to verbatim evidence.
- Unspecified voice, accent, age, gender presentation, personality, and visual
  appearance are labeled artistic casting and are not source identity claims.
- Accent, location, language, and name never determine physical appearance,
  race, ethnicity, nationality, gender, class, or religion.
- Gemma receives the canonical adaptation and its protected terms. It must
  return the same section IDs, evidence, facts, numbers, relationships,
  locations, quotations, and unresolved gaps in first person.
- Generated text passes the source adaptation validator before TTS.
- Generated SDXL prompts preserve scene IDs and grounding and must pass the
  local 68–75-token gate before StreamDiffusionTD can consume them.
- TTS creates a new section timeline, WebVTT, and SRT. Visual boundaries are
  retimed to semantic section links when available, with proportional retiming
  as a compatibility fallback.
- A bundle is promoted atomically only after its requested audio exists. Any
  error leaves the canonical or last-known-good rendition active.

Runtime previews still require editorial review before publication.

## No-model preparation

Check the safe profile without importing Torch, contacting Ollama, loading a
model, or making a paid call:

```powershell
py -3.10 -m home_podcast `
  --config .\storytelling.real-december.json `
  live-storytelling-doctor `
  --profile 3080_safe `
  --skip-ollama
```

Prepare an exact local-work request for one completed canonical narration:

```powershell
py -3.10 -m home_podcast `
  --config .\storytelling.real-december.json `
  prepare-live-variation `
  --narration 2013-12--story-... `
  --profile 5090_live `
  --loop-index 1 `
  --casting-mode interpretive `
  --seed 201312
```

Add `--visuals <canonical-story-visual-scenes.json>` and optionally
`--human-visuals <canonical-human-figure-scenes.json>` when that narration has
reviewed visual plans. Both paths remain independently switchable after local
variation. Preparation writes only a request and reports the exact Ollama-call
and TTS-section ceilings. It does not call Ollama, import Qwen3-TTS, or use a
paid provider.

## 5090 local environment

Use a dedicated Python environment on the 5090. Install PyTorch appropriate to
that machine, then install the official `qwen-tts` package. Cache the selected
Qwen model before a show; the first uncached model load may otherwise contact a
model registry. Do not install or load this environment on the 3080 show path.

The preview configuration uses
`Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign`. Before publication, audition cast and
cross-section continuity. The preferred production upgrade is an approved
local reference-voice bank with the Qwen Base voice-clone model, keeping the
reference rights and consent records outside generated source identity.

Check the 5090 dependencies and local Ollama model:

```powershell
py -3.10 -m home_podcast `
  --config .\storytelling.real-december.json `
  live-storytelling-doctor --profile 5090_live
```

Execute one prepared request explicitly:

```powershell
py -3.10 -m home_podcast `
  --config .\storytelling.real-december.json `
  execute-live-variation `
  --request .\work\storytelling-real-december\runtime\requests\<variant>.json
```

This uses only the configured loopback Ollama endpoint and local Qwen runtime.
It does not use Capriole, ElevenLabs, or any stored API credential.

## Show Control and worker

The Local Variations tab exposes:

- Runtime Profile
- Live Local Variations
- Narration Text Variation
- Local Speech Variation
- Visual Prompt Variation
- Interpretive Casting
- Random Variation Seeds
- Fixed Variation Seed
- Regenerate Next Loop

The controls write `work/storytelling-real-december/runtime/control.json`.
TouchDesigner does not launch model processes. On the 5090, start the worker in
a separate terminal:

```powershell
py -3.10 -m home_podcast `
  --config .\storytelling.real-december.json `
  run-live-storytelling-worker
```

The storytelling sequencer must supply `Current Narration ID` and the optional
canonical narration visual plan on the connector. When Show Control requests a
new generation, the worker writes a private variant directory and promotes a
validated `current.json` pointer. TouchDesigner queues that bundle and switches
its voices-only audio and visual plan only at the next loop boundary.

To control the same file without TouchDesigner:

```powershell
py -3.10 -m home_podcast `
  --config .\storytelling.real-december.json `
  set-live-storytelling `
  --profile 5090_live `
  --enable `
  --narration 2013-12--story-... `
  --narration-variation `
  --speech-variation `
  --visual-variation `
  --casting-mode interpretive `
  --seed-mode random `
  --regenerate
```

Use `--profile 3080_safe --disable` when moving back to the 3080. This causes
the worker to remain disabled and restores canonical playback without loading
local models.

## Runtime files

```text
work/storytelling-real-december/runtime/
  control.json
  status.json
  current.json
  requests/<variant-id>.json
  variants/<variant-id>/
    adaptation.json
    casting-card.json
    visual-scenes.json
    audio/voices-only.wav
    audio/timeline.json
    audio/captions.vtt
    audio/captions.srt
    bundle.json
```

These are rebuildable local runtime files and remain ignored by Git. Canonical
narrations and reviewed publishable artifacts continue to live under
`narrations/real-december`.
