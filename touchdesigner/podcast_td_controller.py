"""TouchDesigner-facing controller for podcast_visualizer.

The parent COMP must provide Scenejson, Humanfigurejson, Visualpath, and
Playheadsec custom parameters plus prompt_out, caption_out, and status_out
Table DAT children. StreamDiffusionTD is accessed through its public
prompt/seed multiparms only.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.util
import json
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
        self.active_live_bundle = None
        self.pending_live_bundle = None
        self.live_runtime_message = "canonical"
        self._refresh_live_bundle(allow_activate=True)
        self.reload()

    def reload(self):
        scene_path = self._selected_scene_path()
        if not self._load_scene(scene_path):
            return
        self.update(float(self.owner_comp.par.Playheadsec.eval()))

    def _load_scene(self, scene_path):
        module_path = self._resolve_path(str(self.owner_comp.par.Sequencermodule.eval()))
        if not Path(scene_path).is_file():
            self._status("error", f"Scene JSON not found: {scene_path}")
            self.sequencer = None
            self.loaded_path = ""
            return False
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
        return True

    def update(self, playhead_seconds):
        requested_playhead_ms = max(0, round(float(playhead_seconds) * 1000.0))
        loop_boundary = self.last_playhead_ms is None
        detected_wrap = False
        if self.sequencer is not None and self.last_playhead_ms is not None:
            edge = max(1_000, min(10_000, self.sequencer.duration_ms // 10))
            detected_wrap = (
                self.last_playhead_ms >= self.sequencer.duration_ms - edge
                and requested_playhead_ms <= edge
            )
            loop_boundary = detected_wrap
        self._refresh_live_bundle(allow_activate=loop_boundary)
        if detected_wrap:
            self._request_random_live_variation()
        selected_path = self._selected_scene_path()
        if selected_path != self.loaded_path:
            if not self._load_scene(selected_path):
                return
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
        table.appendRow(["visual_path", self._visual_path_name()])
        table.appendRow(["scene_json", self.loaded_path])
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
        table.appendRow(["live_runtime", self.live_runtime_message])
        table.appendRow(
            [
                "live_variant_id",
                (
                    self.active_live_bundle.get("variant_id", "")
                    if self.active_live_bundle
                    else ""
                ),
            ]
        )

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

    def _visual_path_name(self):
        parameter = getattr(self.owner_comp.par, "Visualpath", None)
        value = parameter.eval() if parameter is not None else "original"
        if isinstance(value, (int, float)):
            return {1: "human_figures", 2: "balanced"}.get(int(value), "original")
        normalized = str(value or "").strip().casefold().replace(" ", "_")
        if normalized in {
            "1",
            "human",
            "human_figure",
            "human_figures",
            "humanfigures",
        }:
            return "human_figures"
        if normalized in {"2", "balanced", "balanced_memories"}:
            return "balanced"
        return "original"

    def _selected_scene_path(self):
        active_live_bundle = getattr(self, "active_live_bundle", None)
        if active_live_bundle:
            live_visuals = active_live_bundle.get("assets", {}).get("visuals")
            live_path = (
                live_visuals.get(self._visual_path_name())
                if isinstance(live_visuals, dict)
                else live_visuals
            )
            if live_path and Path(str(live_path)).is_file():
                return self._resolve_path(str(live_path))
        parameter_name = {"human_figures": "Humanfigurejson",
                          "balanced": "Balancedjson"}.get(
                              self._visual_path_name(), "Scenejson")
        parameter = getattr(self.owner_comp.par, parameter_name, None)
        if parameter is None or not str(parameter.eval()).strip():
            parameter = self.owner_comp.par.Scenejson
        return self._resolve_path(str(parameter.eval()))

    def _live_variations_enabled(self):
        control = self.owner_comp.op("show_control")
        if control is None:
            return False
        enabled = getattr(control.par, "Livevariations", None)
        profile = getattr(control.par, "Runtimeprofile", None)
        if enabled is None or profile is None or not bool(enabled.eval()):
            return False
        value = profile.eval()
        if isinstance(value, (int, float)):
            return int(value) == 1
        return str(value).strip().casefold().replace(" ", "_") in {
            "5090",
            "5090_live",
            "1",
        }

    def _refresh_live_bundle(self, *, allow_activate):
        if not self._live_variations_enabled():
            if self.active_live_bundle is not None:
                self.active_live_bundle = None
                self.pending_live_bundle = None
                self.last_scene_id = ""
                self._set_voices_audio(self._canonical_audio_path())
            self.live_runtime_message = "canonical"
            return
        current_parameter = getattr(self.owner_comp.par, "Livecurrentjson", None)
        narration_parameter = getattr(self.owner_comp.par, "Currentnarrationid", None)
        if current_parameter is None or narration_parameter is None:
            self.live_runtime_message = "runtime_parameters_missing"
            return
        narration_id = str(narration_parameter.eval()).strip()
        if not narration_id:
            self.live_runtime_message = "waiting_for_narration"
            return
        current_path = Path(self._resolve_path(str(current_parameter.eval())))
        try:
            pointer = json.loads(current_path.read_text(encoding="utf-8-sig"))
            if pointer.get("status") != "ready":
                raise ValueError("current pointer is not ready")
            bundle_path = Path(str(pointer["bundle"]))
            bundle = json.loads(bundle_path.read_text(encoding="utf-8-sig"))
            if bundle.get("status") != "ready":
                raise ValueError("bundle is not ready")
            if bundle.get("narration_id") != narration_id:
                self.live_runtime_message = "ready_for_other_narration"
                return
            audio = bundle.get("assets", {}).get("audio")
            if not audio or not Path(str(audio)).is_file():
                raise ValueError("bundle audio is missing")
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            self.live_runtime_message = "fallback_canonical"
            return
        if (
            self.active_live_bundle is None
            or self.active_live_bundle.get("variant_id") != bundle.get("variant_id")
        ):
            self.pending_live_bundle = bundle
        if allow_activate and self.pending_live_bundle is not None:
            self.active_live_bundle = self.pending_live_bundle
            self.pending_live_bundle = None
            self.last_scene_id = ""
            self.last_streamdiffusion_signature = None
            self._set_voices_audio(self.active_live_bundle["assets"]["audio"])
            self.live_runtime_message = "live_ready"
        elif self.pending_live_bundle is not None:
            self.live_runtime_message = "ready_next_loop"
        else:
            self.live_runtime_message = "live_active"

    def _canonical_audio_path(self):
        parameter = getattr(self.owner_comp.par, "Audiofile", None)
        return str(parameter.eval()) if parameter is not None else ""

    def _set_voices_audio(self, path):
        if not path:
            return
        audio = self.owner_comp.op("voices_only_audio")
        if audio is None:
            return
        try:
            current = str(audio.par.file.eval())
            if current != str(path):
                audio.par.file.val = str(path)
                cue = getattr(audio.par, "cuepulse", None)
                if cue is not None:
                    cue.pulse()
        except Exception:
            self.live_runtime_message = "audio_switch_failed"

    def _request_random_live_variation(self):
        if not self._live_variations_enabled():
            return
        control = self.owner_comp.op("show_control")
        random_parameter = (
            getattr(control.par, "Randomvariationseeds", None)
            if control is not None
            else None
        )
        if random_parameter is None or not bool(random_parameter.eval()):
            return
        callbacks = self.owner_comp.op("show_control/control_callbacks")
        try:
            callbacks.module._write_live_control(regenerate=True)
            self.live_runtime_message = "requested_next_loop"
        except Exception:
            self.live_runtime_message = "variation_request_failed"
