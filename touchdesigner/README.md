# TouchDesigner visual sequencer

Target version: TouchDesigner 2025.32820.

This connector separates editorial timing from the paid generation operator:

```text
selected voices-only or soundscape-only audio / timeline
  -> podcast_visualizer
  -> prompt_out Table DAT
  -> StreamDiffusionTD prompt + seed multiparms

selected original, human-figure or optional balanced visual scene JSON
  -> podcast_visualizer
  -> caption_out + status_out Table DATs
```

`prompt_out` is the stable adapter surface. During a crossfade it contains the
outgoing and incoming prompt chunks, seeds, and smoothstep weights. The
controller copies those rows into every configured StreamDiffusionTD
operator's `Promptdict` and `Seeddict` sequences, enables normalized prompt
weights, and selects `slerp` interpolation. Outside a crossfade it avoids
rewriting an unchanged prompt.

## Visual paths

### Current continuous-image edition (.40)

For a private cross-PC restore without GitHub, use the export/import tool in
[`docs/PORTABLE_SETUP.md`](../docs/PORTABLE_SETUP.md#current-local-first-handoff-136-stories--podcast40toe).
Run **`touchdesigner/rebind_private_handoff.py`** in the imported `.40` after
hash verification, with both servers stopped. It rebases our file parameters
and embedded callback paths without saving, starting models or touching paid
operator/5090 settings. The older pilot-only path rebinder is not suitable.

Use **`podcast.40.toe`**, **2025.32820**, **3080_safe**. It holds the outgoing
approved scene across uncovered intervals, story separators and the loop tail,
then interpolates at the next unchanged approved cue. Incoming details are
never requested early. The held scene is a presentation/transition reference,
not a claim that its source event continues.

- **Scene Interpolation Seconds** and **Playlist → Story / Loop Interpolation
  Seconds:** adjustable, default 3; capped at half the incoming scene. Zero
  explicitly disables interpolation.
- **Playlist → Gap Colour Off (Hold Image):** disabled/read-only at zero. There
  is no automatic colour substitution, including inside a story. Both final
  output routes retain their renderer input through every gap.
- All three visual paths retain 619 reviewed scenes, with 136 stories, 2,862
  captions, unchanged approved audio and the exact one-second separators.
- The unsigned-seed adapter fix and all existing colour/audio/seed controls
  remain intact. The generation servers and live variations stay off in the
  saved project. Start only one selected StreamDiffusionTD server yourself.

Isolated installer, logic tests and native reopen/pixel/control audit receipts:
`work/storytelling-real-december/continuous-image-hold-136-3080-2026-10-30/`.
The previous `.38`, every older project and the 5090 setup remain unchanged.
Tests verify outgoing-scene routing and prompt/seed weights with servers
stopped; model-generated interpolation is not a guaranteed pixel dissolve.

### Preserved all-join interpolation edition (.38)

Use **`podcast.38.toe`** in **2025.32820**, RTX **3080_safe**. It reuses the
entire approved `.36` audio/caption/prompt timeline without changing content.

- **Scene Interpolation Seconds:** default 3; all 483 within-story joins per
  path now interpolate, including the 152 previously forced cuts.
- **Playlist → Story / Loop Interpolation Seconds:** default 3; all 135 story
  joins plus the loop interpolate. Both durations are capped at half the
  incoming scene, and 0 is the explicit off setting.
- **Playlist → Gap Colour Fade Seconds:** default 0.5; handles actual uncovered
  intervals only. It does not insert colour between ordinary scenes/stories
  instead of the requested interpolation.
- Prompt/seed blends begin after the incoming cue; future details are never
  requested early. The previous reviewed prompt may decay during that blend.
  This is generation-conditioning interpolation (`slerp`), not a buffered
  pixel dissolve; the model's returned frames and latency still affect motion.
- The local adapter maps canonical seeds with `seed % 2147483647` before TD
  integer writes, preserving stable repeatability without rewriting source
  seed metadata. The old adapter could abort on seeds above TD's signed
  integer range, leaving a partly updated blend. Both renderer targets now
  receive complete prompt and seed weights throughout every tested join.

Isolated build/runtime/native audits:
`work/storytelling-real-december/interpolated-136-3080-2026-10-30/`.
`.36`, shared controllers and 5090 files remain unchanged. Tests use stopped
model servers and validate multiparm weights/output routing, not live image
quality. Start only your selected StreamDiffusionTD server for the visual test.

### Preserved offline 136-story edition (.36)

Use local **`podcast.36.toe`**, build **2025.32820**, RTX **3080_safe**.
This new edition preserves `.34` and every older/5090 project. It installs
the 24 revised ambient tracks approved from the unified review, together with
the other 112 approved tracks. No narration, prompt wording or caption wording
was generated or rewritten during installation.

- **Audio Source:** Narration Only, Ambient Only, Narration + Ambient.
  All three modes use the **3:18:58.720** clock, with 136 exact one-second silent
  separators (135 interior joins plus the loop tail). No voices overlap.
- **Visual Path:** Contextual/Original, Human Figures, Balanced Memories;
  **619 scenes per path**, minimum five seconds, **2,862 shared captions**.
  Every story has its own opening prompt at its exact start. Later details
  retain their reviewed speech gates. The renderer still needs time to return
  an image after a changed prompt.
- **Playlist → Story / Loop Transition Seconds:** 0–30, default 0. Zero changes
  the incoming prompt immediately; nonzero values reveal the incoming image
  through a soft nonrepresentational colour layer, bounded by half the opening
  scene. This never preloads the next person's prompt into the previous story.
- **Playlist → Soft Colour Transition Seconds:** 0–5, default 0.5. Controls
  semantic-gap fades; an expired event image is fully hidden by abstract colour.
  The existing **Scene Crossfade Seconds** defaults to 1 and remains separate.
- The neutral compositor is wired before colour correction on **both** output
  routes. Brightness, contrast, saturation, gamma and the other existing colour
  controls remain meaningful. Random seeds, navigation, looping and the three
  audio modes remain available. Live local variation stays off.

Build inputs and native installer:
`work/storytelling-real-december/approved-136-five-second-3080-2026-10-30/`.
The installer is edition-specific, not a replacement for shared/5090 code.
Its native audit checks all 136 story openings in all paths, semantic-gap
routing, loop restart and audio decoding. Local colour-fixture pixel tests
verify both final outputs; real parameter/pulse tests verify frame callbacks.
These tests do not assert the editorial quality or latency of live-generated
images. Neither model server is started by installation or tests.

### Full offline storytelling playlist (.28)

Open local `podcast.28.toe` in **2025.32820** on the RTX 3080. All 45 currently
approved stories play in order on one **55:35.680** timeline. The previous
`.27` preserves the preceding 45-story visual edition; `.26` keeps its 35
stories. `.25` and all older / 5090 projects are preserved.

- **Show Control → Audio Source:** Narration Only, Ambient Only, or Narration
  + Ambient. Switching does not restart playback. The mix uses the approved
  narration at unity gain and the already mastered ambient bed at unity gain,
  not the louder solo-audition version. A peak limiter supplies headroom. The
  three files have exactly the same sample count and caption clock.
- **Playlist → Jump to Story:** select any of the 45 stories. This is a jump
  command, not a now-playing indicator; **Now Playing** follows the real clock.
  Previous/Next retain the playing/paused state. Restart Playlist pauses and
  returns to the beginning. Loop Full Playlist wraps all 45; off holds at end.
- **Playlist → Story Edge Fade Seconds:** visual fade through black at each
  story join and the full loop, 0–15 seconds. It never overlaps two narrators.
  **Show Control → Crossfade Seconds** controls within-story scene changes.
- **Visual Path:** Original Story Visuals, Human Figures and Balanced Memories
  now each contain **166 speech-anchored scenes** (498 approved treatments),
  with richer story objects, actions, people and settings. Human Figures keeps
  front-facing portraits with unknown appearance obscured. All paths share the
  same 818 captions and approved audio. `.27` retains the previous 132/132/161
  scenes. Prompt approval is not an assertion of generated-image quality.
- **3080 safety:** canonical playback only; local variation controls are
  locked off in this playlist. Start a single StreamDiffusionTD server yourself
  for visual generation. Installation and audits never start servers.

The `.28` manifest is
`work/storytelling-real-december/playlist-45-detail-2026-10-29/playlist.json`.
It reuses all three `.27` WAVs byte-for-byte; no media rebuild is needed.
The reviewed draft remains in `prompt-detail-45-v2-2026-10-29/`; the separate
`detail-approved-2026-10-29/` per-story plans record the user's prompt approval.
Validate the active edition without loading models:

```powershell
.\.venv-qwen\Scripts\python.exe -m scripts.validate_storytelling_playlist `
  --work-dir work/storytelling-real-december/playlist-45-detail-2026-10-29
```

Historical media rebuild commands (CPU-only; bundled FFmpeg):

```powershell
py -3.10 -m scripts.build_storytelling_playlist
py -3.10 -m scripts.validate_storytelling_playlist
```

Those no-argument commands retain the original 35-story edition for backwards
compatibility. To rebuild the separate 45-story edition from its prepared,
hash-bound collection without repeating the earlier segment conversions:

```powershell
py -3.10 -m scripts.build_storytelling_playlist `
  --collection work/storytelling-real-december/playlist-45-2026-10-29/collection.json `
  --work-dir work/storytelling-real-december/playlist-45-2026-10-29 `
  --audio-dir audio/storytelling-real-december/playlist-45-2026-10-29 `
  --reuse-segments-from work/storytelling-real-december/playlist-35-2026-10-29/segments
.\.venv-qwen\Scripts\python.exe -m scripts.validate_storytelling_playlist `
  --work-dir work/storytelling-real-december/playlist-45-2026-10-29
```

The validator uses NumPy for PCM measurements, not Qwen model weights or CUDA.
The build reused 70 earlier segments read-only and converted only 20 new ones.

Source hashes, source-bound personal-story reviews, visual grounding and exact
WAV durations are checked before assembly. Per-story resampling is cached and
resumable; no speech is cut, sped up or regenerated. Derived ambient copies have
350 ms edge envelopes to avoid clicks at story joins. The optional
`--ambient-db -3` reduces the mixed bed by 3 dB; the default is 0 dB because the
source bed is already quieter than speech. Changing the recipe creates a new
audio edition without overwriting the previous one. Output manifest and audit
receipts for `.27` live in `work/storytelling-real-december/playlist-45-2026-10-29/`;
the three WAVs live in `audio/storytelling-real-december/playlist-45-2026-10-29/`.
These large local folders and paid `.toe` components remain Git-ignored; a
future cross-PC handoff must copy them privately as well as the repository.

To rebind an existing **stopped** 3080 storytelling project, run in TD's Python
Textport, replacing the root with the checkout path:

```python
exec(open(r"C:\Users\wenju\.gemini\antigravity\scratch\home-podcast\touchdesigner\install_storytelling_playlist.py", encoding="utf-8").read())
install(r"C:\Users\wenju\.gemini\antigravity\scratch\home-podcast\work\storytelling-real-december\playlist-45-detail-2026-10-29\playlist.json")
_ = audit()
event_audit()  # muted, actual callbacks and loop/story clock crossings
```

Do not run the older generic Show Control installer over this playlist: that
installer restores the historical podcast's two-track configuration. Save a
**new** file using native File → Save As, then reopen it and run
`_ = audit(saved=True, expected_project='podcast.28.toe')` for `.28`.
The connector's read-only `Playlistmanifest` stores the edition selection so
reopening and callback execution cannot silently fall back to 35 stories.
Projects without this parameter continue using the original 35-story default.
The installer never saves a `.toe` and does
not edit either paid component's internals. `.25`'s legacy Story Test selector
is disabled only in the new playlist; use the Playlist page instead.

On this workstation native Save As also writes the unnumbered `podcast.toe`.
Before future saves, protect its hash and a private byte-identical copy. During
the `.27` save that side effect was detected and the original base file was
restored from the hash-identical preserved `.22`. All earlier numbered projects
and the prior 35-story work/cache remained unchanged. Final receipts are in
the 45-story work directory (`handoff.json`, `td-reopen-audit.json`,
`td-event-audit.json`, `validation.json`).

For `.28`, the same side effect is restored from a verified private
`base-before-save.toe` copy. Its installation, exhaustive prompt-adapter,
callback and reopen receipts live in
`work/storytelling-real-december/playlist-45-detail-2026-10-29/`.
The prompt review page remains available at
`audio/storytelling-real-december/prompt-detail-review-45-v2-2026-10-29/index.html`;
approval is recorded separately so the presented draft and `.27` stay intact.
After changing external plan files, reopen `.28` or use Reload; never start
both StreamDiffusionTD servers. This edition does not enable local narration
or speech generation and does not modify the 5090 configuration.

The RTX 3080 self-narrated test is saved separately as `podcast.25.toe`.
Its Show Control → Visual Path menu adds **Balanced Memories** to the two
preserved paths. The new path covers the 35 currently approved recordings with
124 scenes (versus 95 per retained storytelling path). It varies people,
interactions, places, objects and actions instead of repeating a portrait/room
pattern. Unknown faces use back views and physical crops rather than doubled
reflections. Locations, future wishes and identity claims retain source roles.
`Balancedjson` selects the current story's new plan; the three-story test menu
updates all three paths together. Switching visuals reloads at the same
playhead without restarting audio. Scene boundaries may differ between paths,
but voices, ambient, caption timings and total runtime are identical.

The current story-detail collection is frozen at
`work/storytelling-real-december/rich-visuals-2026-10-29/collection.json`.
All 124 balanced prompts emphasize source-specific objects, actions,
relationships and settings within one 72–75-token SDXL chunk. The library and
river-picnic passages have revised visual onsets; both audio stems, captions
and full runtimes remain unchanged. The previous `.24` collection is preserved
at `work/storytelling-real-december/balanced-visuals-2026-10-29/positive-v2/collection.json`.
The current companion `td_rich.py` is an offline, 3080-only setup/audit helper;
it does not start either paid component. Use native **File → Save As** for new
numbered `.toe` copies, then reopen and verify; `project.save()` may use the
application's numbered-save policy instead. `.24`, `.23`, `.22`, `podcast.toe` and the
5090 project remain separate. The prompt review catalog is
`audio/storytelling-real-december/rich-visual-review-2026-10-29/index.html`.
Actual image quality/identity review is still pending rendering.

For the preserved 30-minute podcast pilot, `Visual Path` switches between `Original Story Visuals`
and `Human Figures`. Both JSON plans contain the same 90 scene IDs, timestamps,
captions, story links, and crossfade boundaries, so selection happens at the
current playhead without restarting or changing audio. The human path keeps
the same locations, actions, objects, and emotional register used to design
the soundscape. It foregrounds a person only when supported by evidence and
uses a front-facing environmental-portrait composition for 88 scenes. Faces
with incomplete identity evidence remain in soft shadow, silhouette,
reflection, diffusion, or archival occlusion; two sensitive scenes preserve
deliberate absence instead of inventing a historically missing perspective.

## Install

The active production project is the RTX 3080 copy: `podcast.toe` or a numbered
`podcast.<revision>.toe`. Open it with TouchDesigner 2025.32820. The `.toe`
remains local and is not part of the Git repository.

For routine 3080 updates, run the guarded updater from a Textport:

```python
exec(open(r"C:\path\to\home-podcast\touchdesigner\update_3080_project.py", encoding="utf-8").read())
```

It accepts `podcast.toe`, numbered `podcast.<revision>.toe` saves, and explicit
`podcast.3080` names. It refreshes the tracked Show Control and callbacks,
rebinds repository paths, recreates the two Spout senders, and leaves the paid
StreamDiffusionTD components and model servers untouched. Inspect the result,
then save a new numbered 3080 revision.

## Audit the 3080 project

Run both guarded control audits after an update:

```python
exec(open(r"C:\path\to\home-podcast\touchdesigner\audit_3080_controls.py", encoding="utf-8").read())
exec(open(r"C:\path\to\home-podcast\touchdesigner\audit_3080_live_events.py", encoding="utf-8").read())
```

The first audit checks every control style and range, callback registration,
audio and image routing, both Spout outputs, both color branches, and the
effect of all sliders, switches, menus, and buttons. It suspends the
Parameter Execute DAT during its transaction, invokes the same callback module
deterministically, and restores the original state.

The second audit changes the same controls on separate TouchDesigner
application frames. That separation verifies the live Parameter Execute event
path rather than reading downstream nodes before their deferred callbacks
cook. Wait for `AUDIT_3080_LIVE_EVENTS`, not only the initial
`AUDIT_3080_LIVE_EVENTS_SCHEDULED` line. Both scripts reject non-podcast
filenames, do not save the `.toe`, and do not start model servers.

For an optional generated-image check, start exactly one configured
StreamDiffusionTD server, wait for its model initialization to finish, and
run:

```python
exec(open(r"C:\path\to\home-podcast\touchdesigner\audit_3080_visuals.py", encoding="utf-8").read())
```

The visual audit requires `Serveractive`, `Streamactive`, a live RTX 3080
backend connection, a current output-memory name, non-black `color_out_*`
pixels, non-black `null*` Spout-source pixels, and no operator errors. It
forces one local output cook so a paused show can prove the generated
shared-memory frame reaches both output chains; this does not change or save
project parameters. Embedded StreamDiffusionTD status tables persist in the
`.toe`, so legacy GPU names, frame counts, connection labels, or errors are
reported but are not accepted as proof of a current session. The timestamp in
the output-memory name is the server-session start time, not a heartbeat, and
therefore remains valid for a long-running show.

Pulse `Stop Stream` on that component after the check and confirm its server
process has exited before starting the other component. Never run both model
servers together.

Only one open TouchDesigner project may listen on a given OSC receive port.
The shipped primary component uses 8574/8583. Close another project using
those ports before testing, or temporarily assign an unused receive/transmit
pair to the active 3080 component and its generated server config. Do not save
temporary diagnostic port overrides into the `.toe`.

Run the full installer only when creating a fresh connector:

```python
exec(open(r"C:\path\to\home-podcast\touchdesigner\install_podcast_connector.py", encoding="utf-8").read())
```

The installer creates `/project1/podcast_visualizer` with:

- `voices_only_audio` and `soundscape_audio`: synchronized pilot audio stems;
- `audiosource_switch`: an exclusive switch feeding the audio device output;
- `show_control`: live playback, audio-source, visual-path, random-seed,
  crossfade, color, and optional local-variation controls;
- `syphonspoutout1` and `syphonspoutout2`: the Spout senders, installed
  from `null1` and `null2` when those output nulls exist;
- `color_out_1` and `color_out_2`: adjusted primary and backup image outputs;
- `prompt_out`: provider-neutral prompt slots and blend weights;
- `caption_out`: current speech-only caption;
- `status_out`: playhead and scene diagnostics;
- `execute_callbacks`: frame callback driving playback;
- `parameter_callbacks`: playhead observer that also updates immediately while
  paused or seeking.

If paid StreamDiffusionTD components are already inside
`/project1/podcast_visualizer`, do not rerun the installer. Set
`Streamdiffusionpath` to a semicolon-separated operator list, for example
`StreamDiffusionTD;StreamDiffusionTD2`, reload the controller, and save the
project. The adapter mirrors prompts into every listed operator. It changes
only public custom parameters; it does not modify the paid components
internally or start their model servers. Run only one model server at a time.

To add or refresh only the show controls in an existing project without
touching StreamDiffusionTD, run:

```python
exec(open(r"C:\path\to\home-podcast\touchdesigner\install_show_control.py", encoding="utf-8").read())
```

After moving the 3080 `.toe` to another computer, save it in the cloned
repository root and run the guarded updater above. For a path-only repair,
run the safe rebinder once:

```python
exec(open(r"C:\path\to\home-podcast\touchdesigner\rebind_project_paths.py", encoding="utf-8").read())
```

The rebinder updates both visual-scene paths plus the audio, sequencer,
controller, and callback paths without deleting, recreating, or starting
either paid StreamDiffusionTD component. Save the `.toe` after checking
playback.

The `Crossfade Seconds` parameter updates immediately while playing, paused,
or seeking. It defaults to 8 seconds and accepts values up to 30 seconds; the
normalized slider range ends at 15, so values from 15 through 30 can be typed
directly. The sequencer caps an extreme value at half the current scene
duration so every scene still reaches full strength and the next transition
remains continuous. Rerunning the show-control installer preserves the current
play, audio-source selection, audio enabled state, seed mode, crossfade, and
color values. `status_out` reports the effective `crossfade_ms`, current
`crossfade_progress`, seed generation, and color-pipeline state.

The same crossfade also spans the loop boundary. Its first half occurs at the
end of the final scene and its second half occurs at the beginning of scene
one, using the same smoothstep weights on both sides. A zero-second crossfade
disables both internal and loop transitions.

`Random Seeds Each Loop` is off by default. Off keeps the scene seeds from the
visual plan, so repeated loops reproduce the same generation. On derives a
new seed bank at every detected timeline wrap while keeping those seeds stable
for seeking and crossfading inside that loop. `New Random Seeds` advances the
bank immediately, and Restart advances it when random mode is enabled.

The Color page controls a Level TOP followed by an HSV Adjust TOP for each
configured StreamDiffusionTD operator:

- Brightness, Contrast, Gamma, Black Level, and Opacity use the Level TOP.
  Brightness `1.0` is neutral, `0.0` is black, and values above `1.0`
  brighten the image.
- Hue Shift, Saturation, and Color Value use the HSV Adjust TOP.
- Color Adjustments Enabled switches between the untouched generator output
  and the adjusted branch without changing the saved neutral settings.
- Reset Color restores neutral values.

The installer safely places the post-processing branch between each paid
generator and its existing downstream output. The stable adjusted endpoints
are `color_out_1` and `color_out_2`; rerunning the installer preserves their
downstream routing and all current show-control values.

The TouchDesigner timeline is the pilot clock. The installer expands its range
to the complete episode, sets both Audio File In CHOPs to `Locked to Timeline`,
and makes `Playheadsec` follow network time. Playing, pausing, and seeking
therefore recompute the visual scene and both audio positions directly.
`Audio Source` selects either `Human Voices Only` or `Soundscape Only`; there
is no combined-track option. Enable `Audio Enabled` only when the selected
track should be sent to the default audio device. Project-load and
timeline-start callbacks resynchronize the timeline, exclusive source switch,
and audio device with the saved Show Control values, so a saved Off state
remains off after reopening the `.toe`. If TouchDesigner advances briefly
during project load, the paused startup guard returns the pilot to frame 1.

The local `.toe` and any `.tox` components are ignored by Git because they may
contain the paid StreamDiffusionTD component.

## Buffered storytelling variations

The Local Variations page is a file-protocol controller for the separate
self-narrated storytelling path. It never starts Ollama, Qwen3-TTS, or a paid
StreamDiffusionTD server.

- `RTX 3080 Safe — Canonical` forces Live Local Variations off and keeps local
  language and speech models unloaded.
- `RTX 5090 Live — Local Variations` permits the separately started local
  worker to prepare text, speech, and casting-aware prompt variations.
- Narration, speech, visual prompt, interpretive casting, and seed behavior can
  be enabled independently.
- `Regenerate Next Loop` increments a request nonce. A completed bundle is
  queued and applied only when the playhead wraps, so current speech is never
  interrupted.
- Missing, late, or invalid bundles retain canonical Codex prompts and cached
  ElevenLabs speech.

The control, status, and current-bundle pointer live under
`work/storytelling-real-december/runtime`. A storytelling sequencer supplies
the connector's `Currentnarrationid` and optional `Canonicalvisuals` values.
The active bundle can replace the voices-only Audio File In path and visual
scene JSON; selecting `Soundscape Only` remains independent.

The guarded 3080 updater sets `3080_safe` and Off. The guarded 5090 updater
sets the capable profile but also leaves generation Off, so updating a project
never loads models. See
[`../docs/LIVE_LOCAL_VARIATIONS.md`](../docs/LIVE_LOCAL_VARIATIONS.md) for the
worker and command-line workflow.
