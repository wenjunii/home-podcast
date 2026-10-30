from __future__ import annotations

import json
import random
import re
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LocalSpeechRender:
    audio_path: Path
    timeline_path: Path
    duration_ms: int
    sections: int
    sample_rate: int


@dataclass(frozen=True)
class LocalSpeechSectionRender:
    audio_path: Path
    duration_ms: int
    sample_rate: int


class Qwen3TTSLocalRenderer:
    """Optional in-process Qwen3-TTS renderer.

    Heavy runtime dependencies and model weights are intentionally optional.
    Importing the project or using the 3080-safe profile never imports Torch,
    downloads a model, or reserves GPU memory.
    """

    def __init__(
        self,
        *,
        model_name: str,
        mode: str = "voice_design",
        device_map: str = "cuda:0",
        dtype: str = "bfloat16",
        attention: str = "sdpa",
    ) -> None:
        if mode not in {"voice_design", "voice_clone", "custom_voice"}:
            raise ValueError(f"Unsupported Qwen3-TTS mode: {mode}")
        self.model_name = model_name
        self.mode = mode
        self.device_map = device_map
        self.dtype = dtype
        self.attention = attention
        self._model = None
        self._voice_clone_prompts: dict[tuple[str, str], Any] = {}

    @staticmethod
    def dependency_status() -> dict[str, Any]:
        missing = []
        for module_name in ("torch", "numpy", "qwen_tts"):
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
        adaptation: dict[str, Any],
        casting_card: dict[str, Any],
        output_dir: Path,
        *,
        speech_seed: int,
    ) -> LocalSpeechRender:
        sections = adaptation.get("sections")
        if not isinstance(sections, list) or not sections:
            raise ValueError("Adaptation requires at least one section")
        output_dir.mkdir(parents=True, exist_ok=True)
        model = self._load_model()
        all_pcm: list[bytes] = []
        timeline_sections = []
        cursor_frames = 0
        sample_rate = 0

        for index, section in enumerate(sections):
            seed = int(speech_seed) + index
            self._seed_everything(seed)
            wavs, current_rate = self._generate(model, section, casting_card)
            if not wavs:
                raise RuntimeError(f"Qwen3-TTS returned no audio for section {index + 1}")
            current_rate = int(current_rate)
            if sample_rate and current_rate != sample_rate:
                raise RuntimeError("Qwen3-TTS changed sample rate between sections")
            sample_rate = current_rate
            pcm = _float_audio_to_pcm16(wavs[0])
            start_ms = round(cursor_frames / sample_rate * 1000)
            frames = len(pcm) // 2
            all_pcm.append(pcm)
            cursor_frames += frames
            speech_end_ms = round(cursor_frames / sample_rate * 1000)
            pause_ms = int(section.get("pause_after_ms") or 0)
            pause_frames = round(sample_rate * pause_ms / 1000)
            if pause_frames:
                all_pcm.append(b"\x00\x00" * pause_frames)
                cursor_frames += pause_frames
            end_ms = round(cursor_frames / sample_rate * 1000)
            timeline_sections.append(
                {
                    "section_id": str(section["section_id"]),
                    "start_ms": start_ms,
                    "speech_end_ms": speech_end_ms,
                    "end_ms": end_ms,
                    "text": str(section["text"]),
                    "speech_seed": seed,
                }
            )

        audio_path = output_dir / "voices-only.wav"
        with wave.open(str(audio_path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(sample_rate)
            handle.writeframes(b"".join(all_pcm))

        duration_ms = round(cursor_frames / sample_rate * 1000)
        timeline = {
            "contract_version": 1,
            "kind": "live_storytelling_timeline",
            "narration_id": adaptation["narration_id"],
            "variant_id": adaptation.get("variant_id"),
            "duration_ms": duration_ms,
            "sample_rate": sample_rate,
            "channels": 1,
            "sections": timeline_sections,
        }
        timeline_path = output_dir / "timeline.json"
        timeline_path.write_text(
            json.dumps(timeline, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        _write_captions(output_dir, timeline_sections)
        return LocalSpeechRender(
            audio_path=audio_path,
            timeline_path=timeline_path,
            duration_ms=duration_ms,
            sections=len(sections),
            sample_rate=sample_rate,
        )

    def render_section(
        self,
        section: dict[str, Any],
        casting_card: dict[str, Any],
        output_path: Path,
        *,
        speech_seed: int,
    ) -> LocalSpeechSectionRender:
        """Render one resumable cache unit without holding a whole story in RAM."""
        if not isinstance(section.get("text"), str) or not section["text"].strip():
            raise ValueError("Speech section requires non-empty text")
        output_path = output_path.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        model = self._load_model()
        self._seed_everything(int(speech_seed))
        wavs, sample_rate = self._generate(model, section, casting_card)
        if not wavs:
            raise RuntimeError("Qwen3-TTS returned no audio for the speech section")
        sample_rate = int(sample_rate)
        pcm = _float_audio_to_pcm16(wavs[0])
        temporary = output_path.with_suffix(".tmp.wav")
        try:
            with wave.open(str(temporary), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(sample_rate)
                handle.writeframes(pcm)
            temporary.replace(output_path)
        finally:
            if temporary.exists():
                temporary.unlink()
        return LocalSpeechSectionRender(
            audio_path=output_path,
            duration_ms=round((len(pcm) // 2) / sample_rate * 1000),
            sample_rate=sample_rate,
        )

    def unload(self) -> None:
        """Release the optional model before another 3080 production phase."""
        self._model = None
        self._voice_clone_prompts.clear()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            return

    def _load_model(self):
        if self._model is not None:
            return self._model
        try:
            import torch
            from qwen_tts import Qwen3TTSModel
        except ImportError as error:
            raise RuntimeError(
                "Local Qwen3-TTS is not installed. Use the 3080-safe profile or "
                "install the optional 5090 runtime environment."
            ) from error
        dtype = getattr(torch, self.dtype, None)
        if dtype is None:
            raise ValueError(f"Unsupported Torch dtype: {self.dtype}")
        self._model = Qwen3TTSModel.from_pretrained(
            self.model_name,
            device_map=self.device_map,
            dtype=dtype,
            attn_implementation=self.attention,
        )
        return self._model

    @staticmethod
    def _seed_everything(seed: int) -> None:
        import numpy
        import torch

        random.seed(seed)
        numpy.random.seed(seed % (2**32))
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)

    def _generate(self, model, section, casting_card):
        text = str(section["text"])
        language = _qwen_language(str(casting_card.get("language") or "en"))
        performance = _performance_instruction(section, casting_card)
        voice = casting_card.get("voice", {})
        common = {
            "text": text,
            "language": language,
        }
        if self.mode == "voice_design":
            return model.generate_voice_design(
                **common,
                instruct=_voice_design_instruction(voice, performance),
            )
        if self.mode == "custom_voice":
            speaker = str(voice.get("speaker") or "").strip()
            if not speaker:
                raise ValueError("Custom-voice casting requires voice.speaker")
            return model.generate_custom_voice(
                **common,
                speaker=speaker,
                instruct=performance,
            )
        reference_audio = str(voice.get("reference_audio") or "").strip()
        reference_text = str(voice.get("reference_text") or "").strip()
        if not reference_audio or not Path(reference_audio).is_file():
            raise ValueError("Voice-clone casting requires an existing reference_audio")
        if not reference_text:
            raise ValueError("Voice-clone casting requires reference_text")
        prompt_key = (str(Path(reference_audio).resolve()), reference_text)
        voice_clone_prompt = self._voice_clone_prompts.get(prompt_key)
        if voice_clone_prompt is None:
            voice_clone_prompt = model.create_voice_clone_prompt(
                ref_audio=reference_audio,
                ref_text=reference_text,
                x_vector_only_mode=False,
            )
            self._voice_clone_prompts[prompt_key] = voice_clone_prompt
        return model.generate_voice_clone(
            **common,
            voice_clone_prompt=voice_clone_prompt,
        )


def _voice_design_instruction(voice: dict[str, Any], performance: str) -> str:
    description = str(voice.get("tts_instruction") or "").strip()
    if not description:
        description = (
            f"An adult {voice.get('gender_presentation', 'androgynous')} voice, "
            f"{voice.get('age_presentation', 'adult')}, speaking in "
            f"{voice.get('accent_profile', 'clear conversational English')}."
        )
    return f"{description} {performance}".strip()


def _performance_instruction(section: dict[str, Any], casting_card: dict[str, Any]) -> str:
    delivery = section.get("delivery", {})
    personality = ", ".join(casting_card.get("personality", []))
    nonverbal = ", ".join(delivery.get("nonverbal", []))
    parts = [
        f"Speak as a {personality} storyteller." if personality else "",
        f"Emotion: {delivery.get('emotion', 'natural and conversational')}.",
        f"Pace: {delivery.get('pace', 'conversational')}.",
        f"Performance details: {nonverbal}." if nonverbal else "",
        str(delivery.get("direction") or ""),
        "Keep every spoken word exactly as supplied; performance directions are not words.",
    ]
    return " ".join(part.strip() for part in parts if part and part.strip())


def _qwen_language(value: str) -> str:
    names = {
        "en": "English",
        "zh": "Chinese",
        "ja": "Japanese",
        "ko": "Korean",
        "de": "German",
        "fr": "French",
        "ru": "Russian",
        "pt": "Portuguese",
        "es": "Spanish",
        "it": "Italian",
    }
    return names.get(value.casefold(), value)


def _float_audio_to_pcm16(value: Any) -> bytes:
    try:
        array = value.detach().cpu().float().numpy()
    except AttributeError:
        import numpy

        array = numpy.asarray(value, dtype=numpy.float32)
    import numpy

    flattened = numpy.asarray(array, dtype=numpy.float32).reshape(-1)
    clipped = numpy.clip(flattened, -1.0, 1.0)
    return (clipped * 32767.0).astype("<i2").tobytes()


def _write_captions(output_dir: Path, sections: list[dict[str, Any]]) -> None:
    vtt = ["WEBVTT", ""]
    srt = []
    for index, section in enumerate(sections, 1):
        start = _timestamp(int(section["start_ms"]), vtt=True)
        end = _timestamp(int(section["speech_end_ms"]), vtt=True)
        text = re.sub(r"\s+", " ", str(section["text"])).strip()
        vtt.extend([str(index), f"{start} --> {end}", text, ""])
        srt.extend(
            [
                str(index),
                f"{_timestamp(int(section['start_ms']), vtt=False)} --> "
                f"{_timestamp(int(section['speech_end_ms']), vtt=False)}",
                text,
                "",
            ]
        )
    (output_dir / "captions.vtt").write_text("\n".join(vtt), encoding="utf-8")
    (output_dir / "captions.srt").write_text("\n".join(srt), encoding="utf-8")


def _timestamp(milliseconds: int, *, vtt: bool) -> str:
    hours, remainder = divmod(max(0, milliseconds), 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    separator = "." if vtt else ","
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{millis:03d}"
