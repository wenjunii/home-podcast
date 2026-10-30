from __future__ import annotations

import random
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LocalAmbientRender:
    audio_path: Path
    duration_ms: int
    sample_rate: int
    channels: int


class StableAudio3LocalRenderer:
    """Lazy Stable Audio 3 adapter for sequential offline production.

    Importing this module never imports Torch, downloads weights, or starts a
    model. Model loading happens only after an explicitly executed local job.
    """

    MODEL_MAX_SECONDS = {
        "small-sfx": 120.0,
        "small-music": 120.0,
        "medium": 380.0,
    }

    def __init__(
        self,
        *,
        model_name: str = "medium",
        device: str = "cuda",
        model_half: bool = True,
        steps: int = 8,
        cfg_scale: float = 1.0,
        chunked_decode: bool = True,
        allow_model_download: bool = False,
    ) -> None:
        if model_name not in self.MODEL_MAX_SECONDS:
            raise ValueError(f"Unsupported Stable Audio 3 model: {model_name}")
        self.model_name = model_name
        self.device = device
        self.model_half = bool(model_half)
        self.steps = max(1, int(steps))
        self.cfg_scale = float(cfg_scale)
        self.chunked_decode = bool(chunked_decode)
        self.allow_model_download = bool(allow_model_download)
        self._model = None

    @staticmethod
    def dependency_status() -> dict[str, Any]:
        missing = []
        for module_name in ("torch", "torchaudio", "stable_audio_3"):
            try:
                __import__(module_name)
            except ImportError:
                missing.append(module_name)
        return {
            "available": not missing,
            "missing_modules": missing,
            "network_calls": 0,
        }

    def render(
        self,
        *,
        prompt: str,
        negative_prompt: str,
        duration_seconds: float,
        seed: int,
        output_path: Path,
    ) -> LocalAmbientRender:
        prompt = str(prompt).strip()
        if not prompt:
            raise ValueError("Stable Audio prompt must not be empty")
        duration_seconds = float(duration_seconds)
        maximum = self.MODEL_MAX_SECONDS[self.model_name]
        if not 1.0 <= duration_seconds <= maximum:
            raise ValueError(
                f"Stable Audio {self.model_name} duration must be 1-{maximum:g} seconds"
            )
        model = self._load_model()
        self._seed_everything(int(seed))
        audio = model.generate(
            prompt=prompt,
            negative_prompt=str(negative_prompt).strip() or None,
            duration=duration_seconds,
            steps=self.steps,
            cfg_scale=self.cfg_scale,
            seed=int(seed),
            batch_size=1,
            sample_size=model.model_config["sample_size"],
            chunked_decode=self.chunked_decode,
        )
        output_path = output_path.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_suffix(".tmp.wav")
        try:
            import torchaudio

            sample_rate = int(model.model.sample_rate)
            waveform = audio[0].detach().cpu()
            torchaudio.save(str(temporary), waveform, sample_rate)
            temporary.replace(output_path)
        finally:
            if temporary.exists():
                temporary.unlink()
        channels = int(waveform.shape[0]) if waveform.ndim > 1 else 1
        return LocalAmbientRender(
            audio_path=output_path,
            duration_ms=round(float(waveform.shape[-1]) / sample_rate * 1000),
            sample_rate=sample_rate,
            channels=channels,
        )

    def unload(self) -> None:
        self._model = None
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            return

    def _load_model(self):
        if self._model is not None:
            return self._model
        previous_offline = os.environ.get("HF_HUB_OFFLINE")
        if not self.allow_model_download:
            os.environ["HF_HUB_OFFLINE"] = "1"
        try:
            try:
                from stable_audio_3 import StableAudioModel
            except ImportError as error:
                raise RuntimeError(
                    "Stable Audio 3 is not installed in the optional local-audio "
                    "environment. Dry-run commands do not require it."
                ) from error
            self._model = StableAudioModel.from_pretrained(
                self.model_name,
                device=self.device,
                model_half=self.model_half,
            )
        finally:
            if previous_offline is None:
                os.environ.pop("HF_HUB_OFFLINE", None)
            else:
                os.environ["HF_HUB_OFFLINE"] = previous_offline
        return self._model

    @staticmethod
    def _seed_everything(seed: int) -> None:
        try:
            import torch
        except ImportError:
            return
        random.seed(seed)
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
