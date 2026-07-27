# TouchDesigner visual sequencer

Target version: TouchDesigner 2025.32820.

This connector separates editorial timing from the paid generation operator:

```text
voices-only audio / timeline
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

Open the current local working revision, `podcast.18.toe`, with TouchDesigner
2025.32820. The `.toe` remains local and is not part of the Git repository. In
a Textport, run the installer only when creating a fresh connector:

```python
exec(open(r"C:\Users\wenju\.gemini\antigravity\scratch\home-podcast\touchdesigner\install_podcast_connector.py", encoding="utf-8").read())
```

The installer creates `/project1/podcast_visualizer` with:

- `voices_only_audio`: local pilot audio source, disabled by default;
- `show_control`: live playback, random-seed, crossfade, and color controls;
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
exec(open(r"C:\Users\wenju\.gemini\antigravity\scratch\home-podcast\touchdesigner\install_show_control.py", encoding="utf-8").read())
```

The `Crossfade Seconds` parameter updates immediately while playing, paused,
or seeking. It defaults to 8 seconds and accepts values up to 30 seconds; the
normalized slider range ends at 15, so values from 15 through 30 can be typed
directly. The sequencer caps an extreme value at half the current scene
duration so every scene still reaches full strength and the next transition
remains continuous. Rerunning the show-control installer preserves the current
play, audio, seed mode, crossfade, and color values. `status_out` reports the
effective `crossfade_ms`, current `crossfade_progress`, seed generation, and
color-pipeline state.

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
to the complete episode, sets Audio File In to `Locked to Timeline`, and makes
`Playheadsec` follow network time. Playing, pausing, and seeking therefore
recompute the visual scene and audio position directly. Enable `Audio Enabled`
only when the voices track should be sent to the default audio device. Project
load and timeline-start callbacks resynchronize the timeline and audio device
with the saved Show Control values, so a saved Off state remains off after
reopening the `.toe`. If TouchDesigner advances briefly during project load,
the paused startup guard returns the pilot to frame 1.

The local `.toe` and any `.tox` components are ignored by Git because they may
contain the paid StreamDiffusionTD component.
