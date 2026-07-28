# TouchDesigner visual sequencer

Target version: TouchDesigner 2025.32820.

This connector separates editorial timing from the paid generation operator:

```text
selected voices-only or soundscape-only audio / timeline
  -> podcast_visualizer
  -> prompt_out Table DAT
  -> StreamDiffusionTD prompt + seed multiparms

visual scene JSON
  -> podcast_visualizer
  -> caption_out + status_out Table DATs
```

`prompt_out` is the stable adapter surface. During a crossfade it contains the
outgoing and incoming prompt chunks, seeds, and smoothstep weights. The
controller copies those rows into every configured StreamDiffusionTD
operator's `Promptdict` and `Seeddict` sequences, enables normalized prompt
weights, and selects `slerp` interpolation. Outside a crossfade it avoids
rewriting an unchanged prompt.

## Install

The active production project is the 5090 copy, `podcast.5090.toe`; its
current numbered save is `podcast.5090.24.toe`. Open it with TouchDesigner
2025.32820. The `.toe` remains local and is not part of the Git repository.
The `podcast.3080*.toe` files are reference inputs only and must not be opened,
updated, or saved as part of 5090 work.

For routine 5090 updates, run the guarded updater from a Textport:

```python
exec(open(r"C:\path\to\home-podcast\touchdesigner\update_5090_project.py", encoding="utf-8").read())
```

It refuses to run unless the open filename is `podcast.5090.toe` or a numbered
5090 revision. It refreshes the tracked Show Control and callbacks, rebinds
repository paths, recreates the two 5090 Spout senders, and leaves the paid
StreamDiffusionTD components and model servers untouched. Inspect the result,
then save a new numbered 5090 revision.

## Audit the 5090 project

Run both guarded control audits after an update:

```python
exec(open(r"C:\path\to\home-podcast\touchdesigner\audit_5090_controls.py", encoding="utf-8").read())
exec(open(r"C:\path\to\home-podcast\touchdesigner\audit_5090_live_events.py", encoding="utf-8").read())
```

The first audit checks every control style and range, callback registration,
audio and image routing, both Spout outputs, both color branches, and the
effect of all 18 sliders, switches, menus, and buttons. It suspends the
Parameter Execute DAT during its transaction, invokes the same callback module
deterministically, and restores the original state.

The second audit changes the same controls on separate TouchDesigner
application frames. That separation verifies the live Parameter Execute event
path rather than reading downstream nodes before their deferred callbacks
cook. Wait for `AUDIT_5090_LIVE_EVENTS`, not only the initial
`AUDIT_5090_LIVE_EVENTS_SCHEDULED` line. Both scripts refuse 3080 filenames,
do not save the `.toe`, and do not start model servers.

For an optional generated-image check, start exactly one configured
StreamDiffusionTD server, wait for its model initialization to finish, and
run:

```python
exec(open(r"C:\path\to\home-podcast\touchdesigner\audit_5090_visuals.py", encoding="utf-8").read())
```

The visual audit requires `Serveractive`, `Streamactive`, a live RTX 5090
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
pair to the active 5090 component and its generated server config. Do not save
temporary diagnostic port overrides into the `.toe`.

Run the full installer only when creating a fresh connector:

```python
exec(open(r"C:\path\to\home-podcast\touchdesigner\install_podcast_connector.py", encoding="utf-8").read())
```

The installer creates `/project1/podcast_visualizer` with:

- `voices_only_audio` and `soundscape_audio`: synchronized pilot audio stems;
- `audiosource_switch`: an exclusive switch feeding the audio device output;
- `show_control`: live playback, audio-source, random-seed, crossfade, and
  color controls;
- `syphonspoutout1` and `syphonspoutout2`: the 5090 Spout senders, installed
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

After moving `podcast.5090.toe` to another computer, save it in the cloned
repository root and run the guarded updater above. For a path-only repair,
run the safe rebinder once:

```python
exec(open(r"C:\path\to\home-podcast\touchdesigner\rebind_project_paths.py", encoding="utf-8").read())
```

The rebinder updates the scene, audio, sequencer, controller, and callback
paths without deleting, recreating, or starting either paid StreamDiffusionTD
component. Save the `.toe` after checking playback.

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
