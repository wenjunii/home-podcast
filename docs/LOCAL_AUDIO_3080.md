# RTX 3080 local initial-audio production

This is the offline initial-render path for the self-narrated December series.
It does not replace the `3080_safe` TouchDesigner playback profile, does not
modify a `.toe`, and does not change the later `5090_live` buffered-variation
path.

New story audio has a **300-second maximum**, including all pauses and tail
silence. Production planning and cached speech jobs use the current storytelling
duration policy; WAV assembly checks the actual complete duration before it can
replace a master. Over-budget stories need one condensed, reviewed version,
not multiple parts.
Nothing is automatically cropped, accelerated, rewritten or regenerated.
The approved 3:40 continuous VoiceDesign experiment remains within this limit;
older long auditions are preserved as experiments rather than new production
deliverables. No 5090 hardware settings or TouchDesigner project are changed by
this shared content policy.

## Current default: one whole-story VoiceDesign take

The approved continuous-voice and volume proofs are now the standard offline
runner, implemented in `home_podcast/single_take_audio.py`. The first ten-story
batch and the second 25-story batch were listening-approved by the user. Their separate immutable approvals are
under `work/storytelling-real-december/local-audio/approvals/`; the earlier
manifest and recordings are unchanged. Audio approval does **not** approve the
automatic captions.

`3080_offline_production` uses the already cached
`Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign` snapshot
`5ecdb67327fd37bb2e042aab12ff7391903235d3`, BF16/SDPA, and one model call for
the complete reviewed text. One casting card, performance direction and seed
stay fixed throughout a story. Emotion and pauses are model instructions, not
spoken stage directions or a guarantee of exact pause lengths. There is no
section stitching, forced speedup, cropping, automatic retry or download.

The reviewed pool currently contains 367 approved personal stories and 48 held
items. Queue selection skips existing takes and defers duplicate candidates
(exact text, same source/title, or identical reviewed witness/title evidence).
Duplicate deferrals do not delete originals or change the editorial holds.
Every selected story still needs an individually reviewed casting brief.

```powershell
.\scripts\run_local_audio_3080.ps1 -Stage PlanSpeech `
  -ProductionIndex .\work\storytelling-real-december\condensation\short-editorial-2026-10-28\approved-production-index.json `
  -NarrationLimit 25
```

After reviewing the selected sources and writing a brief, use a new run ID.
The second batch's reviewed casting brief is
`work/storytelling-real-december/local-audio/production_batch_02_brief.json`.

That batch now contains 25 complete takes totaling 27:11.52, ranging from
21.36 to 155.20 seconds. All passed the duration, speech-content, level and
caption-timing gates, with 2,533 protected existing files verified unchanged.
The listening page is
`audio/storytelling-real-december/production-batch-02-2026-10-28/index.html`.
Listening approval is recorded; caption-editorial approval remains pending. The farmhouse take
uses the separate slow peak-aware mastering fallback described below; the
Decatur take has a documented ASR ending recheck, not an audio edit. Names and
non-English words in the draft captions still need human review.

```powershell
$storyBrief = '.\work\storytelling-real-december\local-audio\production_batch_02_brief.json'
.\scripts\run_local_audio_3080.ps1 -Stage PrepareSpeech -Brief $storyBrief
.\scripts\run_local_audio_3080.ps1 -Stage SpeechDryRun -Brief $storyBrief
# Only after inspecting the dry run; set the exact pending ceiling, not a guess:
.\scripts\run_local_audio_3080.ps1 -Stage RunSpeech -Brief $storyBrief -MaxCalls 25
.\scripts\run_local_audio_3080.ps1 -Stage AuditSpeech -Brief $storyBrief
.\scripts\run_local_audio_3080.ps1 -Stage CheckSpeech -Brief $storyBrief
.\scripts\run_local_audio_3080.ps1 -Stage AssembleSpeech -Brief $storyBrief
.\scripts\run_local_audio_3080.ps1 -Stage VerifySpeech -Brief $storyBrief
```

`AuditSpeech` uses cached CPU Whisper; it and `CheckSpeech` can run on completed
takes while later stories render. A possible missing/repeated passage, failed
duration check or failed mastering check is held rather than silently accepted.
Existing failed/interrupted attempts are never overwritten or retried. Resume
only the untouched pending jobs with their new exact dry-run ceiling. Packaging
requires every take in that batch to pass its technical/content gates.

There is one narrow recognition-error check: if the full-file ASR has recovered
the entire exact script and then assigns at least eight extra outro words to
at most half a second, with mostly zero-duration word timings, it can recheck
the closing audio once, without providing the script as a recognition prompt.
Only an exact recovery of the expected closing passage clears that diagnostic
hold. The original ASR, the closing-audio check and a separate derived report
are retained and hash-bound to the unchanged WAV. Other omissions, additions
or inconclusive rechecks remain held. This is not human listening or caption
approval and never trims the recording.

If earlier small recognition differences prevent that automatic exact-script
tail check, a separate **explicit human check** may resolve only an unspoken,
impossible-timed trailing outro. This requires a hash-bound
`asr-outro-human-review.json`, a cached unprompted closing-audio diagnostic
that recovers an exact suffix of the script, and a separately derived
`asr-report-human-reviewed.json`. The original ASR and complete WAV stay
unchanged. The deterministic gate rejects missing/stale evidence, in-body
removals, normally timed speech, or a different ending. This does not approve
the full voice performance, caption wording or subsequent ambient production.

An in-body ASR omission has a separate human-confirmed recovery gate:
`asr-span-human-review.json` and `asr-report-span-reviewed.json`. It requires
the user's explicit confirmation that the passage is audible, an unprompted
excerpt recognition matching a contiguous source-script window, and positive
measured word timings between the existing neighboring speech. It can remove
only a partial recognized prefix of that same sentence, never other prior
words. Original audio and recognition remain intact; this does not approve
the rest of the captions or the complete voice performance. Do not clear a
genuine TTS omission this way: keep it held for a separately authorized take.

Outputs live at `audio/storytelling-real-december/<run_id>/index.html`, with raw
and leveled WAVs, the exact script transcript, uncorrected ASR transcript, SRT,
VTT, casting metadata and a manifest. CPU ASR is diagnostic, not a listening
score; names and wording still need caption review before publishing or visuals.
After explicit human listening feedback only:

```powershell
.\scripts\run_local_audio_3080.ps1 -Stage ApproveSpeech -Brief $storyBrief `
  -Reviewer '<reviewer>' -ApprovalNote '<actual human listening decision>'
```

The equivalent core CLI is `story-audio` with stages `queue`, `prepare`,
`render`, `audit`, `quality`, `package`, `verify`, and `approve`. Planning and
dry runs never load Qwen or make network calls. Render checks that this is the
idle 3080 workstation and TouchDesigner is closed. The 5090 live path is not
changed. Do not run audio and image models together.

## Consistent speech volume

`config/speech_mastering.json` is the shared **playback mastering** setup for
local initial narration output. It is separate from the selected TTS voice,
emotion, speech seed, and TouchDesigner playback volume. Current defaults:

| Setting | Default | Meaning |
| --- | --- | --- |
| `enabled` | `true` | Create a separate, level-controlled playback master |
| `target_speech_rms_dbfs` | `-22` | Common active-speech level; less negative is louder |
| `correct_volume_drift` | `true` | Counteract gradual fading within a story |
| `analysis_window_seconds` | `8` | Average across phrases rather than chase syllables |
| `maximum_gain_change_db_per_second` | `1` | Limit how quickly the level correction moves |
| `peak_ceiling_dbfs` | `-1.5` | Reserve headroom, checked with 4× oversampling |

This is unweighted active-speech RMS, **not LUFS** and not a guarantee that every
voice is perceptually identical in loudness. The default acceptance tolerance is
2 dB around the target and 3 dB for the beginning-to-end speech-level difference.
If headroom or the maximum safe boost prevents reaching the target, the new copy
is held for review rather than clipped or silently accepted. No fast compressor
or limiter is used: slow gain automation is followed by one headroom adjustment.
For whole-story production only, if that global headroom adjustment alone leaves
the speech too quiet, the runner tries one separately cached, peak-aware copy.
It lowers gain around the peak using the same slow gain-change limit, instead
of lowering the entire story. The original held copy is preserved. Both copies
must meet the same RMS, drift and peak limits; an unresolved problem stays held.
Other quality failures and damaged caches never trigger this fallback. No new
speech generation is involved.
Quiet gaps do not drive up gain. Whisper word timings are used when a matching
ASR report exists; otherwise a local energy gate is used, not semantic VAD.

The finishing step retains the exact sample count, sample rate, words, pauses
and duration. It changes amplitude, not the voice casting or performance. It
does not repair a changed timbre, missing words, or noisy source audio; listening
approval still matters. Raw takes, references, and section caches are untouched.
The soundscape has its own mix policy and is **not** speech-normalized.

The offline `assemble-local-speech` commands automatically use this setup and
record the mastered path as `voices_audio` in the timeline. The standard
whole-story runner applies it in `quality` and `package` for new production runs.
Cached raw TTS calls do not need repeating when the mastering settings change.
Each source/settings/ASR combination gets its own content-keyed playback file and
`mastering.json` receipt. Existing listening masters are not overwritten.

To apply the same setup to an already completed take without speech generation:

```powershell
.\.venv-qwen\Scripts\python.exe -m home_podcast `
  --config .\storytelling.real-december.json master-local-speech `
  --audio "<path-to-original-voices-only.wav>" `
  --output-dir "<path-to-a-new-mastering-folder>" `
  --asr-report "<path-to-matching-asr-report.json>"
```

The ASR argument is optional. NumPy and SciPy are required only for this CPU
processing step; they are already present in the local Qwen environment. For a
fresh audio environment, `pip install -e ".[audio-mastering]"` installs the
optional DSP dependencies without installing or starting a model.

The two reported fading takes have a new review page under
`audio/storytelling-real-december/single-take-reviewed-proof-2026-10-28/volume-stability-v2/index.html`.
The old page, original audio, captions, and the third take are unchanged.
The old frozen generation plan predates the new settings file; do not rewrite its
protected inventory. Use a new generation plan for future runs, or the independent
mastering command above for old takes. The mastering proof separately checks all
2,357 previously protected file hashes and the 38 original proof files.

No TouchDesigner or 5090 live-worker settings were changed. The later live-worker
integration is separate; it must not be described as already normalizing its
output. The shared finishing function is reusable there when that path is enabled
and tested on the 5090.

Historical early content gate, October 28 (superseded by the reviewed pool above):
the old eight audition WAVs are retained for recovery
but are not approved production references. Their input selection included
lyrics and a blog sidebar. Nine stories now have source-backed personal-story
reviews; six were revised. A replacement text-only eight-voice plan is at
`work/storytelling-real-december/local-audio/reviewed-voice-audition-plan.json`
(8 pending local calls, 3,414 characters). It has not been rendered. The normal
`PrepareAudition` runner step can rebuild its default plan from the same reviewed
pool. Always run prepare before trying an old plan; stale plans fail closed.

The installed `qwen-tts` is 0.1.1, matching the latest
[PyPI release](https://pypi.org/project/qwen-tts/) checked on October 28, 2026.
The later [GitHub fine-tuning fix](https://github.com/QwenLM/Qwen3-TTS/commit/022e286b98fbec7e1e916cb940cdf532cd9f488e)
changes the training script, not inference. No runtime or weights were updated
during the content review.

The 3080 performs one model phase at a time. The current path is:

```text
reviewed Codex adaptation
  -> evidence-reviewed casting and delivery brief
  -> one whole-story Qwen VoiceDesign take (resumable per-story cache)
  -> CPU speech check + volume leveling + draft VTT/SRT
  -> human listening and caption review
  -> Stable Audio 3 ambient assets (resumable cache)
  -> continuous soundscape-only track + optional review mix
```

Close TouchDesigner and stop StreamDiffusionTD before an executed phase. Qwen
and Stable Audio are unloaded between phases and are never intentionally held
in VRAM together. The PowerShell runner refuses an executed generation stage
while a TouchDesigner process is open.

## Preserved legacy option: two Qwen models

The following section-cloning approach is retained for recovery and explicit
experiments with `-Profile 3080_legacy_voice_clone`; it is **not** the default.

Qwen documents a VoiceDesign-to-Base workflow: make a short designed reference
voice, review it, and reuse that clip through the Base model's voice-clone
prompt. This gives the collection a stable synthetic voice bank without using
or imitating an unconsenting person's voice.

The production model's main strength is speaker consistency. Its Base
voice-clone API does not expose the same natural-language performance
instruction input as VoiceDesign or 1.7B CustomVoice. Section emotion therefore
comes from the reviewed reference performance, punctuation, wording, and model
sampling. The section delivery metadata is preserved in every job for QA, but
must not be described as guaranteed control. If the audition shows that this
is too flat, do not start a bulk batch; compare the 1.7B CustomVoice
path or keep ElevenLabs as the initial-render fallback.

Official references:

- [Qwen3-TTS repository and VoiceDesign-to-Clone example](https://github.com/QwenLM/Qwen3-TTS)
- [Stable Audio 3 repository and Python API](https://github.com/Stability-AI/stable-audio-3)
- [Stability AI Community License](https://stability.ai/license)

## Runtime setup

Model runtimes are optional and intentionally absent from the project's base
Python dependencies. Use isolated environments so audio packages cannot break
the deterministic catalog and TouchDesigner tools.

Qwen recommends a fresh Python 3.12 environment:

```powershell
py -3.12 -m venv .venv-qwen
.\.venv-qwen\Scripts\python.exe -m pip install --upgrade pip
.\.venv-qwen\Scripts\python.exe -m pip install -e . qwen-tts
```

Install the CUDA/PyTorch build appropriate to the workstation before the last
line when necessary. Model weights are not downloaded by project setup.

Stable Audio 3 Medium is the quality target: it supports up to 380-second
assets and the official benchmark reports roughly 5.1-6.5 GB peak VRAM,
depending on duration and chunked decoding. Medium requires Flash Attention 2.
On this Windows workstation, use a tested WSL2 CUDA environment for Medium if a
matching native Windows Flash Attention build is unavailable. The official
`small-sfx` model is a CPU-capable fallback with a 120-second maximum; change
the local profile only after auditioning its ambient quality. The fallback is
already defined as `3080_native_windows_fallback` and can be selected with
`-Profile 3080_native_windows_fallback` on the runner.

For that native fallback, install the official Stable Audio project outside
this repository and point the runner at its isolated Python:

```powershell
git clone https://github.com/Stability-AI/stable-audio-3 C:\AI\stable-audio-3
Set-Location C:\AI\stable-audio-3
uv sync
.\.venv\Scripts\python.exe -m pip install -e C:\path\to\home-podcast
Set-Location C:\path\to\home-podcast
.\scripts\run_local_audio_3080.ps1 `
  -Stage DoctorAmbient `
  -Profile 3080_native_windows_fallback `
  -StableAudioPython C:\AI\stable-audio-3\.venv\Scripts\python.exe
```

Do not run those installation commands until the model license and disk use
have been reviewed. For Medium under WSL2, run the ambient prepare, generation,
and assembly commands inside the same WSL checkout so absolute job paths stay
consistent; do not prepare Windows-path jobs and execute them under Linux.

Do not commit either environment, model weights, generated caches, or license
tokens. The generated audio tree is ignored by Git.

## Current dry-run gate

Check dependencies without importing either model:

```powershell
.\scripts\run_local_audio_3080.ps1 -Stage Doctor
```

After both isolated environments exist, check each runtime from its own Python
without loading model weights:

```powershell
.\scripts\run_local_audio_3080.ps1 -Stage DoctorQwen
.\scripts\run_local_audio_3080.ps1 -Stage DoctorAmbient
```

Create the representative VoiceDesign plan and show the exact local-call
ceiling:

```powershell
.\scripts\run_local_audio_3080.ps1 -Stage PrepareAudition
.\scripts\run_local_audio_3080.ps1 -Stage AuditionDryRun
```

The current plan contains eight synthetic voice designs and eight pending
local model calls. It deliberately samples narrations without explicit
identity constraints. Accent, gender presentation, age presentation, and
personality are labeled artistic casting, never source identity.

To execute only after setup, license review, and closing TouchDesigner:

```powershell
.\scripts\run_local_audio_3080.ps1 `
  -Stage RunAudition `
  -MaxCalls 8 `
  -AllowModelDownload
```

Omit `-AllowModelDownload` when local model paths have been filled in under
`config/local_audio_production.json` for Qwen. Stable Audio's official loader
uses its managed Hugging Face cache: without the flag, the adapter forces cache-
only mode; with the flag, it may fetch missing weights after license access has
been configured.

Listen to every audition outside the pipeline. Approve only a voice that is
natural, emotionally responsive, intelligible, non-caricatured, and stable:

```powershell
py -3.10 -m home_podcast `
  --config .\storytelling.real-december.json `
  approve-local-voice `
  --plan .\work\storytelling-real-december\local-audio\voice-audition-plan.json `
  --voice-id <voice-id> `
  --reviewer <reviewer-name>
```

Approval records the generated reference in `config/local_voice_roster.json`.
Generated reference WAV files are local and must be copied separately when
moving production to another workstation.

## Legacy section-cloning proof

Prepare three narrations first:

```powershell
.\scripts\run_local_audio_3080.ps1 -Stage PrepareSpeech -Profile 3080_legacy_voice_clone -NarrationLimit 3
.\scripts\run_local_audio_3080.ps1 -Stage SpeechDryRun -Profile 3080_legacy_voice_clone
```

The preparer requires a current source-backed personal-story review for every
narration, including auditions. Historical conservative copies remain blocked
unless individually rewritten and reviewed. `-AllowConservativeEditions` is retained
for CLI compatibility but cannot override the content gate. Hash-bound review
also prevents old plans or cached audio from silently using superseded text.

Use the exact pending number from the dry run:

```powershell
.\scripts\run_local_audio_3080.ps1 -Stage RunSpeech -Profile 3080_legacy_voice_clone -MaxCalls <pending>
.\scripts\run_local_audio_3080.ps1 -Stage AssembleSpeech -Profile 3080_legacy_voice_clone -NarrationLimit 3
```

Review voice identity, mispronunciation, long-form drift, nonverbal behavior,
clipping, silence, and caption timing. Only then expand to the editorially
approved collection. The previous 2,937-section ceiling and roughly 60-hour
estimate include rejected or unreviewed text and are not production estimates.
Rerun preparation for the exact current ceiling; section hashes keep it resumable.

## Continuous ambient track

### GPU ambient audition on the 3080 Ti

The current three-story audition is at
`audio/storytelling-real-december/ambient-audition-2026-10-28/audible-v3/index.html`.
It contains six generated assets, continuous soundscape-only stems, louder solo
inspection copies, and mixes with the approved voices. The three finished
soundscapes total 147.28 seconds. All tracks keep the full narration duration;
specific cues use word timestamps and fade in after their subjects are spoken.

This explicit experiment uses the official public Stable Audio 3 Small-SFX
FP16 ONNX graph through ONNX Runtime CUDA on the RTX 3080 Ti. Text encoding
and audio decoding use the official LiteRT CPU models. The execution profile
verified 26,016 CUDA matrix operations. Six renders produced 224.36 seconds
of source assets in 20.307 seconds after model loading; this is a measured
small-batch result, not a throughput guarantee for the full collection.

The separate runtime is under `work/storytelling-real-december/ambient-runtime`.
Its model receipt pins `stabilityai/stable-audio-3-optimized` at
`08b17423649b5714b22eab20f96bf00751f2358a`; the upstream code is pinned at
`77e0398c26f7d22d801ec1bb036307e8b231f741`. Native Windows CUDA uses
`onnxruntime-gpu==1.26.0` with the workstation's existing CUDA 12.8 DLLs;
no speech model is imported. Dependencies and model files were downloaded
during setup; generation itself ran offline with no paid API calls. Keep this
runtime separate from the speech environment.

```powershell
$ambientProof = '.\work\storytelling-real-december\ambient-audition-2026-10-28\run_audition.py'
py -3.10 $ambientProof dry-run
# The completed audition has zero pending calls. Do not regenerate it.
.\.venv-qwen\Scripts\python.exe $ambientProof verify
$ambientFinisher = '.\work\storytelling-real-december\ambient-audition-2026-10-28\level_ambient.py'
py -3.10 $ambientFinisher dry-run
.\.venv-qwen\Scripts\python.exe $ambientFinisher verify
```

The frozen brief, exact source evidence, seeds, cue times, attempts, generated
asset receipts, GPU profile, and verification are retained under the matching
`work/` directory. Each fresh asset requires one bounded local call; completed
assets are hash-checked and reused. Failed attempts require explicit review.
The earlier `balanced` edition used -32 dBFS RMS, which was insufficient for
the house asset: over 99% of its spectral energy was below 150 Hz. A new
37.68-second room-air asset replaces it only in the `audible-v3` edition.
The original raw asset, earlier mixes, all approved voices, and cue times are
preserved. This one additional offline GPU call took 5.094 seconds after loading.

### Shared ambient level standard

`config/ambient_mastering.json` controls every new local ambient generation:

- Source assets: **-24 LUFS**, true peak at most **-3 dBTP**.
- Completed background stems: **-30 LUFS**, true peak at most **-7 dBTP**.
- Raised solo inspection copies: **-23 LUFS**, true peak at most **-3 dBTP**.

The CPU-only finisher in `home_podcast/ambient_mastering.py` uses two-pass
FFmpeg EBU R128 normalization, independent output measurement, gentle rumble
filtering for raw assets, and bounded peak limiting when needed. Accepted
copies must land within 0.7 LU of their target. A 150–8000 Hz band check holds
assets whose useful sound would disappear on small speakers; it is a technical
screen, not a guarantee for every playback device. Silence, missing the level
target, excessive peaks, and changed duration/channels block promotion.

Integrated loudness and that broad band check are not sufficient on their own:
the first production batch's story 10 passed both while concentrating about
97% of its energy below 250 Hz. New `ambient-batch` plans therefore also freeze
`config/ambient_audibility.json`. Continuous base assets and finished stems
must contain at least 5% of their spectral energy at 250–8000 Hz and lose no
more than 6 dB on a mono downmix. These CPU checks do not collapse or alter the
stereo recording. Before looping environmental material, the assembler selects
a stable body outside generated edge fades, bounded to 12 seconds or 15% at
each end, then holds loops with a three-second RMS dip over 6 dB relative to
their median. Speech is never trimmed or looped by this code. Intended scene
changes, speech ducking and final start/end fades remain; this is not a command
to flatten an entire soundtrack. Frozen older plans keep their original policy.
Human listening remains necessary even when all technical checks pass.

In this audition all six assets measure -24.10 to -23.99 LUFS, and the three
completed stems measure -30.06 to -30.00 LUFS. Matching integrated loudness
does not flatten every moment: gentle scene changes, speech ducking, and
start/end fades remain. CPU speech detection found no words in all six
finished assets; human listening for relevance, music, voices and balance is
still pending.

Raw files are immutable. Level copies live under content-addressed
`ambient-mastered/<hash>/` directories with source/settings/tool hashes,
measured loudness, peaks, audibility results, and quality holds. Local ambient
generation automatically finishes each new asset. Executing a cached job can
finish it without loading any model or making another generation call. Local
soundscape assembly resolves these copies, finishes its complete stem to the
same shared target, and writes a separate `ambient-editions/<hash>` package.
The combined local preview uses the finished stem, not differently leveled
raw cues. The legacy podcast mixer remains unchanged.

The audition is now user-approved, recorded separately under
`work/storytelling-real-december/local-audio/approvals/ambient-audition-2026-10-28-audible-v3.json`.
That approval covers only those three soundscapes, not future assets or captions.
The tested CUDA backend is promoted into the explicit `ambient-batch` production
path below. Legacy provider configurations, TouchDesigner, podcast artifacts
and 5090 settings remain unchanged.

Upstream references: [official runtime](https://github.com/Stability-AI/stable-audio-3),
[optimized public models](https://huggingface.co/stabilityai/stable-audio-3-optimized),
[ONNX Runtime CUDA compatibility](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html).

### Resumable GPU ambient batches

The supported `ambient-batch` command uses
`home_podcast/providers/ambient_gpu.py` and the existing isolated runtime.
It loads no model for planning, dry-run, quality, packaging, or verification.
The executed render launches one explicit worker in the pinned GPU environment,
refuses an active TouchDesigner or a non-3080 workstation, verifies model files
and sampler revision, and checks actual CUDA matrix execution before its raw
assets become reusable caches. Automatic downloads are not supported.

The first production brief is
`work/storytelling-real-december/local-audio/ambient-production-batch-01-2026-10-28/brief.json`.
It covers the first ten listening-approved narrations (13:44.72), with 17
generated source assets. The evening-fire and passing-courier effects are
omitted because their post-mention spans are under 15 seconds. The continuous
background covers those passages. The original longest background uses one
120-second source with an overlap loop to cover the full 174.88-second
narration; the separate volume-corrected edition below repairs its quiet join.
No speech is shortened, stretched, re-generated or cut into sections.

```powershell
$ambientBatch = '.\work\storytelling-real-december\local-audio\ambient-production-batch-01-2026-10-28\brief.json'
py -3.10 -m home_podcast --config storytelling.real-december.json ambient-batch prepare --brief $ambientBatch
py -3.10 -m home_podcast --config storytelling.real-december.json ambient-batch dry-run --brief $ambientBatch
# A fresh version of this exact plan needed 17 local calls; completed assets need zero.
# Only use --execute and --max-calls when a new dry-run reports pending work.
py -3.10 -m home_podcast --config storytelling.real-december.json ambient-batch render --brief $ambientBatch --execute --max-calls 17
py -3.10 -m home_podcast --config storytelling.real-december.json ambient-batch quality --brief $ambientBatch
.\.venv-qwen\Scripts\python.exe -m home_podcast --config storytelling.real-december.json ambient-batch audit --brief $ambientBatch
.\.venv-qwen\Scripts\python.exe -m home_podcast --config storytelling.real-december.json ambient-batch package --brief $ambientBatch
.\.venv-qwen\Scripts\python.exe -m home_podcast --config storytelling.real-december.json ambient-batch verify --brief $ambientBatch
```

The last three commands use the existing audio Python environment for CPU ASR
or numerical assembly; they do not load Qwen or use the GPU. The equivalent
PowerShell stages are `PrepareAmbientBatch`, `AmbientBatchDryRun`,
`RunAmbientBatch -MaxCalls <exact-pending>`, `CheckAmbientBatch`,
`AuditAmbientBatch`, `PackageAmbientBatch`, and `VerifyAmbientBatch`, all with
`-Brief $ambientBatch`.

Each plan freezes current source-backed personal-story reviews, speech listening
approval, exact evidence, ASR word anchors, voice hashes, level settings and
protected original files. New sound choices belong in a new run/brief, never an
edit to a frozen plan. Generation caches are keyed by prompt, negative prompt,
duration, seed, settings and pinned backend revisions; evidence and cue timing
remain traceable separately. A failed or partial attempt is held, never retried
automatically. A completed render resumes with zero model loads and zero calls.

This batch generated 1,002.48 seconds of raw sound in 79.769 seconds after model
loading. The saved execution profile verified 63,223 CUDA matrix operations.
All 17 source assets passed the original shared level/audibility gates (-24.10 to -23.94
LUFS), with no replacement calls needed. CPU screening recognized no words;
it does not rule out nonverbal vocals or music. Listen before approving.
The ten completed production stems measure -30.08 to -30.00 LUFS, and the
raised solo previews -23.09 to -23.00 LUFS. Each retains the exact approved
narration duration. Previous audition audio remains byte-for-byte unchanged.

The original listening package is
`audio/storytelling-real-december/ambient-production-batch-01-2026-10-28/index.html`.
For every story it presents the unchanged approved voice, a matched solo
ambient preview, a combined preview, a quieter production ambient stem,
transcript, existing draft captions and evidence-grounded sound choices.
The new batch has its own pending listening review. None of the old podcast
tracks, three approved audition soundscapes, `.toe` projects or 5090 profiles
are replaced. The legacy Torch/Medium and fallback adapters below stay opt-in.

#### Story 10 volume repair

Use this separate listening edition for the current review:
`audio/storytelling-real-december/ambient-production-batch-01-2026-10-28/volume-v2/index.html#story-10`.
Only **Allowed Home, but Unable to Stay** changes. Its original spectrum was
almost entirely below 250 Hz, and a native generated fade created a quiet
hole around 114–117 seconds despite a passing integrated loudness result.
The repair reuses the human-approved diffuse room-air source from the
three-story audition as non-locating artistic accompaniment, not a historical
reconstruction of Dux or any other setting. It excludes generated edge fades
from derived loop material, preserving the complete original source recording.

The repaired 174.88-second production stem measures -30.00 LUFS, and its solo
preview -23.00 LUFS. Midrange energy is 30.6%, mono loss 3.60 dB, and the largest
three-second interior dip is 1.94 dB. All nine other stories' three listening
files, every original narration, and 184 protected input/output files are
unchanged. No new generation, GPU model loading, network or paid calls were
needed. The user has approved the corrected ambient-only soundscape, recorded
in `work/storytelling-real-december/local-audio/approvals/ambient-production-batch-01-2026-10-28-volume-v2-story-10.json`.
That record does not bulk-approve the other nine soundscapes, the combined mix,
captions, or future sounds.

The frozen repair plan and verification receipt are under
`work/storytelling-real-december/local-audio/ambient-production-batch-01-2026-10-28/volume-v2/`.
The repair runner is beside that directory, `repair_volume.py`; its
`prepare`, `assemble`, and `verify` stages use the existing audio environment
and refuse to replace differing finished audio. The original batch plan and
listening package are untouched, so rerunning the old batch does not silently
apply this correction.

#### Ambient production batch 02

The next ten stories from the listening-approved speech batch 02, excluding
the three already-approved ambient audition stories, have a separate package:
`audio/storytelling-real-december/ambient-production-batch-02-audible-v2-2026-10-28/index.html`.
Total duration is 615.52 seconds (10:15.52). The longest narration is 118.40
seconds; none was rewritten, shortened, stretched or re-generated.

The original brief under
`work/storytelling-real-december/local-audio/ambient-production-batch-02-2026-10-28/`
required exactly 13 local GPU calls. It rendered 722.78 seconds of raw audio
in 58.502 seconds after loading, with 56,368 CUDA matrix operations verified.
The GPU model was unloaded. The new midrange check held the apartment air
asset (only 0.27% midrange energy); the original raw file, plan and quality
hold remain intact. There is no automatic retry or silent edit to that plan.

The corrected, separately frozen brief is
`work/storytelling-real-december/local-audio/ambient-production-batch-02-audible-v2-2026-10-28/brief.json`.
It uses all twelve passing cached assets and no new model calls. The apartment
story shares the passing 71.68-second non-locating house-air asset with
**What I Couldn't Yet Understand**, looping its stable body to 113.36 seconds.
This is artistic domestic accompaniment, not a historical or Chicago-specific
acoustic reconstruction. The optional integer `asset_duration_ms` makes that
source reuse explicit in the cue; it must be 1,000–120,000 ms and no longer
than the cue. Prompt, seed, actual source duration and backend still determine
the exact cache identity; the full cue timing is unchanged. A different source
choice always belongs in a new brief/run, not a changed frozen plan.

All twelve active source assets pass level and audibility screening, measuring
-24.21 to -23.99 LUFS. CPU screening found zero recognized speech segments and
zero VAD speech seconds, which is not proof of no unwanted vocals or music.
Completed stems measure -30.05 to -29.94 LUFS; raised solo previews measure
-23.07 to -23.00 LUFS. Finished midrange energy is at least 22.5%, and mono loss
is no greater than 3.83 dB. The user has approved all ten ambient soundscapes,
recorded in
`work/storytelling-real-december/local-audio/approvals/ambient-production-batch-02-audible-v2-2026-10-28.json`.
That approval does not cover future sounds or captions, which retain their
separate pending editorial status.

Use the standard `ambient-batch` stages above with the corrected brief for
resumption. Its dry-run reports twelve cached assets, zero pending calls and
zero blocked attempts. No paid API, network generation, downloads, podcast
changes, `.toe` writes or 5090 changes are part of this batch. The final twelve
stories from the approved speech batch are covered by batch 03 below; the
three previously approved audition soundscapes stay intact.

#### Ambient production batch 03

The last twelve stories in the current approved speech queue use
`work/storytelling-real-december/local-audio/ambient-production-batch-03-audible-v4-2026-10-28/brief.json`.
The listening page is
`audio/storytelling-real-december/ambient-production-batch-03-audible-v4-2026-10-28/index.html`.
Total narration duration is 868.72 seconds (14:28.72); the longest is 155.20
seconds. Narration, transcripts and caption timing are unchanged.

The original bounded render made 13 new local calls, adding to four cached
assets. It rendered 882.88 seconds of raw sound in 66.956 seconds after loading,
with 56,368 CUDA matrix operations verified and the model subsequently unloaded.
Four candidate backgrounds remain preserved but unused: one failed midrange
audibility, two failed mono compatibility, and one produced a 10.80 dB loop
dip. Separate corrected briefs reuse compatible cached textures rather than
retrying generation or relaxing acceptance gates. The active edition uses
fourteen unique source assets, nine new and five from earlier batches. Its
dry-run has zero pending calls. Exact background substitutions and unchanged
cue anchors are recorded beside the current brief in `replacements.json`.

The final short Lethe scene also exposed a native generated fade inside the
finished stem. Its bed now uses a passing neutral loop body while retaining
the river cue and its word anchor. The eleven previously completed stories'
33 listening WAVs were copied and verified byte-identical; only paths in the
copied cache metadata were mechanically relocated. Old files are untouched.
The one-time `carry_forward.py` receipt verified 99 original files unchanged;
resume the final edition with the normal batch commands, not another copy.

Six specific layers start after their ASR word anchors: country birds and a
distant truck, a river trickle, book pages, Christmas cards, small-purchase
material texture, and distant Shenandoah water. Foundation excavation (4.66
seconds) and a bicycle recollection (2.02 seconds) are skipped; continuous air
remains. No songs, human background voices, brand jingles, invented conflict,
funeral rituals or religious ceremonies are requested. These are illustrative
sounds, not recordings of the people, places or past events.

This batch also caught a finisher edge case: a solo preview could already meet
the LUFS target but exceed the true-peak ceiling, causing the old correction
loop to stop early and correctly hold the output. New batch plans now freeze
`solo_mastering_revision: ambient-lufs-audibility-v2-peak-safe`. That revision
uses bounded oversampled limiting for peak-only violations and remeasures
both level and peak, with the same -23 LUFS target and -3 dBTP ceiling. Its
derivatives have distinct cache identities; sources and older derivatives are
preserved. Frozen plans without this field still use v1, and asset/stem
mastering defaults remain unchanged. The previously held reading preview
passes the new revision at -23.06 LUFS and -3.47 dBTP with identical duration.
Do not edit an older frozen plan to change its mastering revision.

All fourteen active source assets pass quality gates at -24.13 to -24.00 LUFS.
Automated screening found zero words and zero VAD speech seconds; human review
for relevance, unwanted voices/music and comfortable balance is still required.
The new twelve soundscapes have no listening approval yet, and caption
editorial approval is separate. No paid calls, downloads, speech generation,
TouchDesigner writes or 5090 changes are part of this work.

The final edition verifies all twelve exact narration durations and cue anchors,
with 36 audio players and 170 protected inputs unchanged. Production stems
measure -30.01 to -29.91 LUFS; solo previews measure -23.06 to -22.99 LUFS, with
true peaks no higher than -3.00 dBTP. Finished midrange energy is at least
19.5%, and mono loss is at most 4.11 dB. The source substitutions did not
change evidence excerpts or cue anchors. All 284 unit tests pass (three
optional skips), and all 39 focused tests pass in the audio environment.
`queue-coverage.json` accounts for all 35 current approved narrations with no
missing or duplicate ambient story IDs. It separately lists pending listening
review; having a soundtrack is not listening approval or collection-wide
completion. Use the final v4 brief for resumption, not the preserved held or
partial editions. Further work is listening review, caption proofreading and
then audio-aligned visuals, without changing the old podcast artifacts.

### Ambient batch 04 for the next ten stories

The user approved all ten performances in
`audio/storytelling-real-december/production-batch-03-2026-10-29/index.html`.
The immutable approval is
`work/storytelling-real-december/local-audio/approvals/production-batch-03-2026-10-29.json`.
It approves narration listening only, not draft captions or new ambient mixes.
The earlier speech handoff remains a historical pre-approval snapshot.

Resume the corrected ambient edition with the normal stages and this brief:

```powershell
$ambientBatch = '.\work\storytelling-real-december\local-audio\ambient-production-batch-04-audible-v2-2026-10-29\brief.json'
.\scripts\run_local_audio_3080.ps1 -Stage AmbientBatchDryRun -Brief $ambientBatch
.\scripts\run_local_audio_3080.ps1 -Stage CheckAmbientBatch -Brief $ambientBatch
.\scripts\run_local_audio_3080.ps1 -Stage AuditAmbientBatch -Brief $ambientBatch
.\scripts\run_local_audio_3080.ps1 -Stage PackageAmbientBatch -Brief $ambientBatch
.\scripts\run_local_audio_3080.ps1 -Stage VerifyAmbientBatch -Brief $ambientBatch
```

The original brief generated three bounded source sounds (68.36 seconds): soft
volleyball contacts, ceramic mug contacts, and a short neutral-air candidate.
Actual CUDA execution is recorded with 13,008 matrix operations; the model
unloaded after generation. The short candidate passed integrated level checks
but had an early native fade. Its original WAV, plan, quality and speech-screen
receipts remain intact, with a separate `short-base-editorial-hold.json`.
The corrected edition uses seven cached assets and needs zero additional calls.

An explicitly sized continuous **base** can now reuse a longer environmental
source, up to the existing 120-second cap. Assembly uses only the exact story
clock; it never extends the story or changes speech. The default requested
source length is unchanged. Specific-event assets remain bounded by their
evidence-timed spans. This lets the 17.6-second family-memory fragment use the
stable opening of a tested 78-second non-locating room-air texture instead of
the fading short candidate. It does not transfer identity, ancestry or location.

The ten stories total 879.44 seconds (14:39.440). Four specific layers follow
speech anchors: study pages, volleyball contacts, farmhouse mugs and family
research paper. Key sign-out (7 seconds) and shared-meal crockery (14.32 seconds)
are skipped; continuous backgrounds remain. Unfulfilled tiny-house/RV wishes
do not trigger construction or vehicle sounds. No ethnic music, inferred
ceremonies, crying, hospital sounds or reconstructed deathbed events are used.

The separate listening page is
`audio/storytelling-real-december/ambient-production-batch-04-audible-v2-2026-10-29/index.html`.
All ten approved voice recordings are unchanged. Production stems retain the
shared -30 LUFS target, solo previews -23 LUFS, gentle edge fades and speech
ducking. The 30 players are three choices per story, not three independently
generated narrations. The user has now approved these ten soundscapes, recorded
in `work/storytelling-real-december/local-audio/approvals/ambient-production-batch-04-audible-v2-2026-10-29.json`.
Historical manifests and the pre-approval handoff are unchanged. Caption review
remains separate; automated no-word screening does not prove an absence of all
vocal or musical artifacts. No new playlist or `.toe` version has been saved, no
5090 setting has changed, and no paid calls or downloads were made.

Final verification checks all ten exact story durations, cue anchors, 30 audio
players and 156 protected files. Stems measure -30.09 to -29.94 LUFS; solo
previews -23.08 to -22.97 LUFS. An independent interior-level audit excludes
intentional edge fades and finds no dropouts or three-second dips over the
existing 6 dB limit (worst 5.763 dB; the corrected short story 1.307 dB).
These technical checks do not constitute human listening approval.
`verification.json`, `finished-level-audit.json` and `handoff.json` beside the
corrected brief record the results and outstanding review gates. The full
suite passes 304 tests (three optional skips); all 30 focused tests also pass
in the audio environment without skips.

For the full regression suite on this workstation, put the bundled FFmpeg 9
first on the **current process** path. Temporary test projects do not contain
the production project's bundled-tool directory; without this, an older Conda
FFmpeg can be selected and lacks the limiter and mixer options under test.
No system-wide environment change is needed:

```powershell
$batchFfmpegDir = (Resolve-Path -LiteralPath '.\work\storytelling-real-december\tools\ffmpeg-9.0.2\ffmpeg-9.0.2-essentials_build\bin').Path
$env:PATH = $batchFfmpegDir + ';' + $env:PATH
py -3.10 -m unittest discover -s tests
```

### Caption review for the next ten stories

Use the readable edition:
`audio/storytelling-real-december/caption-review-10-readable-v2-2026-10-29/index.html`.
It covers only the ten newly listening-approved voices and ambiences, not the
35-story playlist already in `.26`. The page has ten unchanged voice players,
live captions, click-to-seek lines and nine explicit wording checks in six
stories. The **Only stories with wording checks** button narrows the review.
Each story provides SRT, VTT, the caption transcript and the original script.

All 24 script/recognizer differences received individual editorial decisions.
Fifteen short clips (77.84 seconds total) were recognized by the already cached
Whisper medium model on CPU, with no script prompt, download or network call.
These diagnostics are evidence, not a substitute for hearing the recording.
Twenty-one decisions correct spelling, numeric/compound rendering or provisionally
remove very short recognizer echoes. Three apparent performed variations are
retained: `I drift`, `He died` and `with the baby`, instead of forcing the script.
Seven provisional echo removals, `a change` versus `to change`, and the Wildomar
pronunciation remain seekable listening checks. Source spelling does not prove
pronunciation. No voice recording is edited or regenerated.

The initial edited edition has 215 cues. Its separate readability revision has
216 cues and the same caption transcript bytes for every story, with improved
name/phrase boundaries and fewer dangling function words. Both editions and all
306 original draft cues are preserved. Final captions use the existing word
anchors, at most two 42-character lines and seven seconds per cue, with no
overlaps, out-of-bounds cues or fast-reading warnings. Read-back checks verify
40 transcript/caption files, 52 local links, all ten real WAV durations, 427
protected inputs and exact live-page/export agreement. An offline DOM-stub test
exercises all 216 live cues, 225 seek buttons, one-player-at-a-time behavior and
the review filters (688 assertions); it is not native-browser visual QA.

Rebuild or validate the readable edition without new generation:

```powershell
py -3.10 .\work\storytelling-real-december\caption-review-10-readable-v2-2026-10-29\compile_readable.py --dry-run
py -3.10 .\work\storytelling-real-december\caption-review-10-readable-v2-2026-10-29\compile_readable.py
py -3.10 .\work\storytelling-real-december\caption-review-10-readable-v2-2026-10-29\compile_readable.py --validate
```

The full project suite passes 304 tests (three optional skips); 18 caption/reflow
tests also pass. The user has now accepted this caption edition: the exact
decision, ten story IDs, 216 cues, previously visible wording checks and file
hashes are recorded in
`work/storytelling-real-december/local-audio/approvals/caption-review-10-readable-v2-2026-10-29.json`.
The historical review manifests remain unchanged. Overall caption acceptance
does not prove a place-name pronunciation or authorize speech repair. New
visual production uses this approved clock; no `.toe` overwrite, playlist
promotion, 5090 change or GitHub write is part of this stage.

### Three visual paths for the next ten stories

The staged prompt review is
`audio/storytelling-real-december/visual-review-next-10-2026-10-29/index.html`.
It covers the ten newly approved stories only, with 37 memory scenes per path
and 111 separately authored treatments. **Contextual** emphasizes setting and
objects, **Human figures** requests 37 front-facing environmental portraits
with unsupported facial traits unreadable, and **Balanced memories** uses new
close-ups, actions, relationships and environmental compositions rather than
alternately copying the other paths. The three paths share scene boundaries,
216 approved captions and the same 879.44-second audio clock.

Source details include the temporary college browsing-room residence,
humanities reading, the orange-grove gathering, the librarian's encouragement,
the London television, volleyball practice, welcomed extra children, the
farmhouse's tight kitchen and white boxes, the market tote, the small obituary
notice and the family photograph. Sparse reflections use restrained supported
human/domestic context instead of invented travel props or decor. Ancestry
claims stay reported rather than visually verified. The tiny home is explicitly
imagined; the Seattle parent's return to Wildomar remains unresolved.
The fixed soundscapes remain illustrative, not literal archival field recordings;
their existing continuous bases and timed paper/ball/mug layers are linked in
each scene's `ambient_context`, without re-editing audio for the visual pass.

Authoring and deterministic records live under
`work/storytelling-real-december/visuals-next-10-2026-10-29/`.
Current imports and collection are in its `refined-v2/` subdirectory. Source jobs,
caption approval, personal-story reviews, voice/ambient hashes and exact evidence
are frozen before writing. Initial imported drafts remain intact. The refined
edition preserves the 4K aesthetic cue outside relocated exclusion text,
restores a back-view instruction and points to the tested local sequencer
wrapper. Its selected prompts are 71–75 content tokens under both cached SDXL
tokenizers, with no automatic factual shortening or local token repair.
“4K photography” does not claim native 4K generation.

Resume using the already installed tokenizer environment; these commands do
not load Qwen speech weights, use a text API or start an image model:

```powershell
.\.venv-qwen\Scripts\python.exe .\work\storytelling-real-december\visuals-next-10-2026-10-29\compile.py --refined-v2
.\.venv-qwen\Scripts\python.exe .\work\storytelling-real-december\visuals-next-10-2026-10-29\compile.py --refined-v2 --import-staged
py -3.10 .\work\storytelling-real-december\visuals-next-10-2026-10-29\package.py
.\.venv-qwen\Scripts\python.exe .\work\storytelling-real-december\visuals-next-10-2026-10-29\validate.py
```

All 30 plans pass personal-story, source-evidence, token and timing gates.
Read-back verifies 132 exact location/identity claim instances, holds from
15.82 to 34.38 seconds and 106,188 timing probes at fade overrides of 0, 8, 20
and 60 seconds. No positive-weight future prompt appears before its spoken
anchor. Long fades remain capped at half the incoming hold; the existing
one-second story-edge opacity envelope does not preview a future story.
All 510 protected inputs remain unchanged. The page's 70 direct links and all
embedded audio choices exist, and live caption/prompt data match the JSON plans.

The review page switches visual paths while keeping the same audio time, and
offers narration only, production ambient stem, narration plus ambient and
raised ambient-only review. Its fade input is a **preview**, not the native
Show Control. An offline DOM-stub test exercises all 111 selected treatments,
648 live caption updates, 111 seek actions, four audio choices and long fade
settings (1,687 assertions). All eight focused tests and 304 project tests pass
(three optional skips in the project suite). Native browser/TouchDesigner
operation and actual generated images have not been tested in this stage.

Human visual editorial approval remains **pending** for the active 111 prompts.
No narration, soundscape, published episode, runtime bundle, `.26`, controller
or 5090 configuration is replaced; no network, paid generation or GitHub write
occurred. After prompt approval, the next step is a separately authorized
TouchDesigner/playlist test, preserving `.26` and its 35-story collection.

### 45-story TouchDesigner edition (.27)

The user approved the presented 111 next-ten prompt treatments and a separate
`podcast.27.toe` save. The new playlist appends those ten stories after the
previous 35, preserving their source audio, caption text, prompt compositions,
casting and seeds. Only the playlist clocks are offset. This is a reviewed
45-story subset, not completion of all December stories.

The edition runs **55:35.680**, with **818 captions** and **132 / 132 / 161**
scenes in Original Story Visuals / Human Figures / Balanced Memories. All three
audio modes share exactly 160,112,640 stereo sample frames at 48 kHz. Their
independent PCM check found zero clipped samples. The new build reuses all 70
earlier converted segments read-only and converts only the 20 newly appended
voice/ambient segments; it does not regenerate speech, soundscapes or prompts.

Receipts and the frozen merged collection are under
`work/storytelling-real-december/playlist-45-2026-10-29/`; derived three-mode
WAVs are under `audio/storytelling-real-december/playlist-45-2026-10-29/`.
Prompt approval is separately recorded in
`work/storytelling-real-december/local-audio/approvals/visual-review-next-10-2026-10-29.json`.
The offline validator passes 32,514 boundary probes and verifies 478 protected
inputs. Native installation passes 1,387 checks; actual callbacks pass 27
events, including all ten appended story choices and real timeline crossings.
After native Save As and reopening `.27`, all 1,399 saved-project checks and
all 27 callback events pass again. The selected playlist manifest survives
reopening; all three paths retain 818 captions and the same locked audio clock.
The project suite passes 306 tests with three optional skips.
Native Save As also changed the unnumbered base `podcast.toe`; its exact
original bytes were restored from the hash-identical preserved `.22`, and the
side-effect copy is retained in the new work directory. `.27` remains saved
and verified separately. No earlier numbered `.toe` was overwritten.

The setup remains 3080-safe: paused, balanced visuals, combined audio, fixed
image seeds, 8-second scene fade and 1-second story-edge fade. Local live
variation is locked off and both StreamDiffusionTD servers remain stopped.
Actual generated-image review is still pending. `.26`, previous recordings,
the historical podcast and the separate 5090 configuration are preserved.
No network/paid generation, GitHub sync or publication occurred in this step.
See the [playlist installation instructions](../touchdesigner/README.md#full-offline-storytelling-playlist-28).

### Approved source-detail prompt edition (.28)

The 45-story / 55:35.680 playlist now has a separate `podcast.28.toe`
TouchDesigner 2025.32820 edition. The user approved the presented source-detail
revision: 166 memory beats per path, 498 prompt treatments across Contextual,
Human Figures and Balanced Memories. All three paths now share speech-anchored
timing, with 15-second minimum holds and post-onset crossfades. The 818 captions
and all three `.27` playlist WAVs are reused unchanged; no audio generation,
mastering or mixing pass is needed for this prompt-only update.

The selected manifest and native verification receipts are under
`work/storytelling-real-december/playlist-45-detail-2026-10-29/`.
The staged review and all old visual editions remain intact; approved copies
live in each story's `visuals/detail-approved-2026-10-29/` directory. Prompt
approval does not approve actual generated images, which still need a visual
test. `.27`, all original recordings, the podcast plan and the 5090 setup are
preserved. Installation/audits keep both model servers stopped and the
`3080_safe` live-variation switch off. No GitHub sync is implied by this update.

### Existing collection commands

Ambient planning begins only after actual speech timelines exist:

```powershell
.\scripts\run_local_audio_3080.ps1 -Stage PrepareAmbient -NarrationLimit 3
.\scripts\run_local_audio_3080.ps1 -Stage AmbientDryRun
```

Each narration receives a quiet base layer for its complete duration. Eligible
sections receive a specific acoustic layer grounded in literal sound words in
the narration; a section shorter than 15 seconds inherits the prior texture.
Every prompt excludes speech, voices, singing, and identity inference. These
are illustrative synthetic sounds, never represented as archival recordings.

After listening to the prompt/section match, run the exact ceiling and assemble
the independent tracks:

```powershell
.\scripts\run_local_audio_3080.ps1 -Stage RunAmbient -MaxCalls <pending>
.\scripts\run_local_audio_3080.ps1 -Stage AssembleSoundscape -NarrationLimit 3
```

The assembly writes voices-only and soundscape-only outputs. A combined file is
for review; TouchDesigner can continue selecting the two independent stems.

## Full order and 5090 handoff

Run the collection in this order: audition, voice approval, three-story speech
proof, three-story ambient proof, full speech, speech assembly, full ambient,
soundscape assembly. Never skip the two proof batches.

The canonical 3080 outputs remain the fallback on the 5090. Later, the 5090
worker may generate a future Gemma/Qwen rendition into a complete validated
buffer and atomically promote it at the next loop. It never mutates these
canonical section caches.
