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

Open the current local working revision, `podcast.7.toe`, with TouchDesigner
2025.32820. The `.toe` remains local and is not part of the Git repository. In
a Textport, run the installer only when creating a fresh connector:

```python
exec(open(r"C:\Users\wenju\.gemini\antigravity\scratch\home-podcast\touchdesigner\install_podcast_connector.py", encoding="utf-8").read())
```

The installer creates `/project1/podcast_visualizer` with:

- `voices_only_audio`: local pilot audio source, disabled by default;
- `show_control`: live play, audio, restart, reload, and crossfade controls;
- `prompt_out`: provider-neutral prompt slots and blend weights;
- `caption_out`: current speech-only caption;
- `status_out`: playhead and scene diagnostics;
- `execute_callbacks`: frame callback driving playback;
- `parameter_callbacks`: playhead observer that also updates immediately while
  paused or seeking.

If paid StreamDiffusionTD components are already inside
`/project1/podcast_visualizer`, do not rerun the installer. Set
`Streamdiffusionpath` to a semicolon-separated operator list, for example
`StreamDiffusionTD;StreamDiffusionTD1`, reload the controller, and save the
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
play, audio, and crossfade values. `status_out` reports the effective
`crossfade_ms` and current `crossfade_progress`.

The TouchDesigner timeline is the pilot clock. The installer expands its range
to the complete episode, sets Audio File In to `Locked to Timeline`, and makes
`Playheadsec` follow network time. Playing, pausing, and seeking therefore
recompute the visual scene and audio position directly. Enable `Audio Enabled`
only when the voices track should be sent to the default audio device.

The local `.toe` and any `.tox` components are ignored by Git because they may
contain the paid StreamDiffusionTD component.
