"""TouchDesigner-facing controller for podcast_visualizer.

The parent COMP must provide Scenejson and Playheadsec custom parameters plus
prompt_out, caption_out, and status_out Table DAT children. StreamDiffusionTD is
accessed through its public prompt/seed multiparms only.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import sys


class PodcastVisualController:
    def __init__(self, owner_comp):
        self.owner_comp = owner_comp
        self.sequencer = None
        self.loaded_path = ""
        self.last_scene_id = ""
        self.last_streamdiffusion_signature = None
        self.reload()

    def reload(self):
        scene_path = self._resolve_path(str(self.owner_comp.par.Scenejson.eval()))
        module_path = self._resolve_path(str(self.owner_comp.par.Sequencermodule.eval()))
        if not Path(scene_path).is_file():
            self._status("error", f"Scene JSON not found: {scene_path}")
            self.sequencer = None
            return
        spec = importlib.util.spec_from_file_location(
            "recovered_homes_podcast_sequencer",
            module_path,
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.sequencer = module.PodcastSequencer.from_path(scene_path)
        self.loaded_path = scene_path
        self.last_scene_id = ""
        self.last_streamdiffusion_signature = None
        self.update(float(self.owner_comp.par.Playheadsec.eval()))

    def update(self, playhead_seconds):
        if self.sequencer is None:
            return
        frame = self.sequencer.at(
            float(playhead_seconds) * 1000.0,
            crossfade_ms=self._show_control_crossfade_ms(),
        )
        self._write_prompts(frame)
        self._write_caption(frame)
        adapter_state = self._write_streamdiffusion(frame)
        self._write_status(frame, adapter_state)
        self.last_scene_id = frame.scene_id

    def _show_control_crossfade_ms(self):
        show_control = self.owner_comp.op("show_control")
        if show_control is None:
            return None
        parameter = getattr(show_control.par, "Crossfadesec", None)
        if parameter is None:
            return None
        try:
            return max(0, round(float(parameter.eval()) * 1000))
        except (TypeError, ValueError):
            return None

    def _write_prompts(self, frame):
        table = self.owner_comp.op("prompt_out")
        table.clear()
        table.appendRow(["slot", "scene_id", "role", "concept", "weight", "seed"])
        for slot, layer in enumerate(frame.prompt_layers):
            table.appendRow(
                [
                    slot,
                    layer.scene_id,
                    layer.role,
                    layer.text,
                    f"{layer.weight:.6f}",
                    layer.seed,
                ]
            )

    def _write_caption(self, frame):
        table = self.owner_comp.op("caption_out")
        table.clear()
        table.appendRow(["caption_id", "speaker", "text"])
        table.appendRow(
            [
                frame.caption_id or "",
                frame.caption_speaker,
                frame.caption_text,
            ]
        )

    def _write_streamdiffusion(self, frame):
        layers = list(frame.prompt_layers)
        if not layers:
            return "connected_no_prompt"
        if len(layers) > 2:
            return "error_too_many_prompt_layers"

        target_spec = str(
            self.owner_comp.par.Streamdiffusionpath.eval()
        ).strip()
        target_paths = [
            path.strip()
            for path in re.split(r"[;,\n]+", target_spec)
            if path.strip()
        ] or ["StreamDiffusionTD"]
        signature = (
            tuple(target_paths),
            tuple(
                (
                    layer.scene_id,
                    layer.text,
                    round(float(layer.weight), 6),
                    int(layer.seed),
                )
                for layer in layers
            )
        )
        if signature == self.last_streamdiffusion_signature:
            return (
                "connected"
                if len(target_paths) == 1
                else f"connected:{len(target_paths)}"
            )

        connected = 0
        errors = []
        for target_path in target_paths:
            target = self.owner_comp.op(target_path)
            if target is None:
                errors.append(f"{target_path}:missing")
                continue
            state = self._write_streamdiffusion_target(target, layers)
            if state == "connected":
                connected += 1
            else:
                errors.append(f"{target_path}:{state}")

        if connected == len(target_paths):
            self.last_streamdiffusion_signature = signature
            return (
                "connected"
                if connected == 1
                else f"connected:{connected}"
            )
        self.last_streamdiffusion_signature = None
        if connected:
            return f"partial_connected:{connected}/{len(target_paths)}"
        if len(target_paths) == 1 and errors[0].endswith(":missing"):
            return "adapter_pending"
        return "error_no_streamdiffusion_targets_connected"

    @staticmethod
    def _write_streamdiffusion_target(target, layers):
        try:
            prompt_blocks = getattr(target.par, "Promptdict", None)
            prompt_sequence = getattr(prompt_blocks, "sequence", None)
            if prompt_sequence is None:
                return "error_prompt_multiparm_missing"
            prompt_sequence.numBlocks = len(layers)

            seed_blocks = getattr(target.par, "Seeddict", None)
            seed_sequence = getattr(seed_blocks, "sequence", None)
            if seed_sequence is not None:
                seed_sequence.numBlocks = len(layers)

            for index, layer in enumerate(layers):
                prompt_block = prompt_sequence[index]
                concept = getattr(prompt_block.par, "Concept", None)
                prompt_weight = getattr(prompt_block.par, "Weight", None)
                if concept is None or prompt_weight is None:
                    return f"error_prompt_block_{index}_missing"
                concept.val = layer.text
                prompt_weight.val = float(layer.weight)

                seed_block = seed_sequence[index] if seed_sequence else None
                seed_value = (
                    getattr(seed_block.par, "Seedval", None)
                    if seed_block is not None
                    else None
                )
                seed_weight = (
                    getattr(seed_block.par, "Seedweight", None)
                    if seed_block is not None
                    else None
                )
                if seed_value is not None:
                    seed_value.val = int(layer.seed)
                if seed_weight is not None:
                    seed_weight.val = float(layer.weight)

            normalize = getattr(target.par, "Normpweights", None)
            if normalize is not None:
                normalize.val = True
            interpolation = getattr(target.par, "Setinterpolation", None)
            if interpolation is not None:
                interpolation.val = "slerp"
        except Exception as error:
            return f"error_{type(error).__name__}"

        return "connected"

    def _write_status(self, frame, adapter_state):
        table = self.owner_comp.op("status_out")
        table.clear()
        table.appendRow(["key", "value"])
        table.appendRow(["state", "ready"])
        table.appendRow(["playhead_ms", frame.playhead_ms])
        table.appendRow(["scene_id", frame.scene_id])
        table.appendRow(["scene_index", frame.scene_index])
        table.appendRow(["scene_progress", f"{frame.scene_progress:.6f}"])
        table.appendRow(["crossfade_ms", frame.crossfade_ms])
        table.appendRow(
            ["crossfade_progress", f"{frame.crossfade_progress:.6f}"]
        )
        table.appendRow(["prompt_layers", len(frame.prompt_layers)])
        table.appendRow(["streamdiffusion", adapter_state])

    def _status(self, state, message):
        table = self.owner_comp.op("status_out")
        if table is None:
            return
        table.clear()
        table.appendRow(["key", "value"])
        table.appendRow(["state", state])
        table.appendRow(["message", message])

    @staticmethod
    def _resolve_path(value):
        path = Path(value)
        if path.is_absolute():
            return str(path)
        return str((Path(project.folder) / path).resolve())
