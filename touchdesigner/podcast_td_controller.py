"""TouchDesigner-facing controller for podcast_visualizer.

The parent COMP must provide Scenejson and Playheadsec custom parameters plus
prompt_out, caption_out, and status_out Table DAT children. StreamDiffusionTD is
accessed through its public prompt/seed multiparms only.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
from pathlib import Path
import re
import secrets
import sys


MAX_STREAMDIFFUSION_SEED = 2_147_483_647


@dataclass(frozen=True)
class ControlledPromptLayer:
    scene_id: str
    role: str
    text: str
    weight: float
    seed: int


class PodcastVisualController:
    def __init__(self, owner_comp):
        self.owner_comp = owner_comp
        self.sequencer = None
        self.loaded_path = ""
        self.last_scene_id = ""
        self.last_streamdiffusion_signature = None
        self.last_color_signature = None
        self.last_playhead_ms = None
        self.seed_salt = secrets.randbits(64)
        self.seed_generation = 0
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
        self.last_color_signature = None
        self.last_playhead_ms = None
        self.update(float(self.owner_comp.par.Playheadsec.eval()))

    def update(self, playhead_seconds):
        if self.sequencer is None:
            return
        playhead_ms = max(
            0,
            min(
                round(float(playhead_seconds) * 1000.0),
                self.sequencer.duration_ms,
            ),
        )
        self._advance_loop_seed_if_needed(playhead_ms)
        frame = self.sequencer.at(
            playhead_ms,
            crossfade_ms=self._show_control_crossfade_ms(),
        )
        layers = self._controlled_prompt_layers(frame)
        self._write_prompts(frame, layers)
        self._write_caption(frame)
        adapter_state = self._write_streamdiffusion(frame, layers)
        color_state = self._write_color_controls()
        self._write_status(
            frame,
            layers,
            adapter_state,
            color_state,
        )
        self.last_scene_id = frame.scene_id
        self.last_playhead_ms = frame.playhead_ms

    def randomize_seeds(self):
        self.seed_salt = secrets.randbits(64)
        self.seed_generation += 1
        self.last_streamdiffusion_signature = None

    def advance_seed_loop(self):
        if self._random_seeds_enabled():
            self.seed_generation += 1
            self.last_streamdiffusion_signature = None
        self.last_playhead_ms = None

    def _advance_loop_seed_if_needed(self, playhead_ms):
        if (
            not self._random_seeds_enabled()
            or self.last_playhead_ms is None
            or self.sequencer is None
        ):
            return
        fade_ms = self._show_control_crossfade_ms() or 0
        edge_window = max(
            1_000,
            min(
                self.sequencer.duration_ms // 4,
                fade_ms // 2 + 1_000,
            ),
        )
        if (
            self.last_playhead_ms
            >= self.sequencer.duration_ms - edge_window
            and playhead_ms <= edge_window
        ):
            self.seed_generation += 1
            self.last_streamdiffusion_signature = None

    def _random_seeds_enabled(self):
        show_control = self.owner_comp.op("show_control")
        if show_control is None:
            return False
        parameter = getattr(show_control.par, "Randomseeds", None)
        return bool(parameter.eval()) if parameter is not None else False

    def _controlled_prompt_layers(self, frame):
        layers = list(frame.prompt_layers)
        if not self._random_seeds_enabled() or self.sequencer is None:
            return layers

        first_scene_id = str(self.sequencer.scenes[0]["scene_id"])
        last_scene_id = str(self.sequencer.scenes[-1]["scene_id"])
        last_scene_index = len(self.sequencer.scenes) - 1
        controlled = []
        for layer in layers:
            generation = self.seed_generation
            if (
                frame.scene_index == last_scene_index
                and layer.scene_id == first_scene_id
            ):
                generation += 1
            elif frame.scene_index == 0 and layer.scene_id == last_scene_id:
                generation -= 1
            controlled.append(
                ControlledPromptLayer(
                    scene_id=layer.scene_id,
                    role=layer.role,
                    text=layer.text,
                    weight=float(layer.weight),
                    seed=self._derived_seed(
                        int(layer.seed),
                        generation,
                    ),
                )
            )
        return controlled

    def _derived_seed(self, base_seed, generation):
        payload = (
            f"{int(base_seed)}:{self.seed_salt}:{int(generation)}"
        ).encode("utf-8")
        digest = hashlib.blake2b(payload, digest_size=8).digest()
        return int.from_bytes(digest, "big") % MAX_STREAMDIFFUSION_SEED

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

    def _write_prompts(self, frame, layers=None):
        layers = list(frame.prompt_layers) if layers is None else list(layers)
        table = self.owner_comp.op("prompt_out")
        table.clear()
        table.appendRow(["slot", "scene_id", "role", "concept", "weight", "seed"])
        for slot, layer in enumerate(layers):
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

    def _write_streamdiffusion(self, frame, layers=None):
        layers = list(frame.prompt_layers) if layers is None else list(layers)
        if not layers:
            return "connected_no_prompt"
        if len(layers) > 2:
            return "error_too_many_prompt_layers"

        target_paths = self._target_paths()
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

    def _write_color_controls(self):
        show_control = self.owner_comp.op("show_control")
        if show_control is None:
            return "controls_missing"

        values = {
            "enabled": self._control_value("Colorenabled", True, bool),
            "brightness": self._control_value("Brightness", 1.0, float),
            "contrast": self._control_value("Contrast", 1.0, float),
            "gamma": self._control_value("Gamma", 1.0, float),
            "blacklevel": self._control_value("Blacklevel", 0.0, float),
            "opacity": self._control_value("Opacity", 1.0, float),
            "hue": self._control_value("Hue", 0.0, float),
            "saturation": self._control_value("Saturation", 1.0, float),
            "value": self._control_value("Value", 1.0, float),
        }
        target_paths = self._target_paths()
        signature = (
            tuple(target_paths),
            tuple(values.items()),
        )
        if signature == self.last_color_signature:
            return (
                "connected"
                if len(target_paths) == 1
                else f"connected:{len(target_paths)}"
            )

        connected = 0
        for index, _target_path in enumerate(target_paths, start=1):
            level = self.owner_comp.op(f"color_level_{index}")
            hsv = self.owner_comp.op(f"color_hsv_{index}")
            switch = self.owner_comp.op(f"color_switch_{index}")
            if level is None or hsv is None or switch is None:
                continue
            try:
                level.par.brightness1.val = values["brightness"]
                level.par.contrast.val = values["contrast"]
                level.par.gamma1.val = values["gamma"]
                level.par.blacklevel.val = values["blacklevel"]
                level.par.opacity.val = values["opacity"]
                hsv.par.hueoffset.val = values["hue"] % 360.0
                hsv.par.saturationmult.val = values["saturation"]
                hsv.par.valuemult.val = values["value"]
                switch.par.index.val = 1 if values["enabled"] else 0
            except Exception:
                continue
            connected += 1

        if connected == len(target_paths):
            self.last_color_signature = signature
            return (
                "connected"
                if connected == 1
                else f"connected:{connected}"
            )
        self.last_color_signature = None
        if connected:
            return f"partial_connected:{connected}/{len(target_paths)}"
        return "color_pipeline_pending"

    def _control_value(self, name, default, converter):
        show_control = self.owner_comp.op("show_control")
        parameter = (
            getattr(show_control.par, name, None)
            if show_control is not None
            else None
        )
        if parameter is None:
            return default
        try:
            return converter(parameter.eval())
        except (TypeError, ValueError):
            return default

    def _target_paths(self):
        target_spec = str(
            self.owner_comp.par.Streamdiffusionpath.eval()
        ).strip()
        return [
            path.strip()
            for path in re.split(r"[;,\n]+", target_spec)
            if path.strip()
        ] or ["StreamDiffusionTD"]

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

    def _write_status(self, frame, layers, adapter_state, color_state):
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
        table.appendRow(["prompt_layers", len(layers)])
        table.appendRow(
            [
                "seed_mode",
                "random_per_loop"
                if self._random_seeds_enabled()
                else "stable",
            ]
        )
        table.appendRow(["seed_generation", self.seed_generation])
        table.appendRow(["streamdiffusion", adapter_state])
        table.appendRow(["color", color_state])

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
