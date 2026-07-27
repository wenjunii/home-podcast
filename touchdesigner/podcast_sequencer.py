"""Pure-Python timing core for the Recovered Homes TouchDesigner connector.

This file intentionally imports no TouchDesigner modules so its timing, seeking,
caption, and crossfade behavior can be tested outside TouchDesigner.
"""

from __future__ import annotations

import bisect
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PromptLayer:
    scene_id: str
    role: str
    text: str
    weight: float
    seed: int


@dataclass(frozen=True)
class SequencerFrame:
    playhead_ms: int
    scene_id: str
    scene_index: int
    scene_progress: float
    crossfade_ms: int
    crossfade_progress: float
    caption_id: str | None
    caption_speaker: str
    caption_text: str
    prompt_layers: tuple[PromptLayer, ...]


class PodcastSequencer:
    def __init__(self, plan: dict[str, Any]) -> None:
        scenes = plan.get("scenes")
        captions = plan.get("captions")
        if not isinstance(scenes, list) or not scenes:
            raise ValueError("Visual plan contains no scenes")
        if not isinstance(captions, list):
            raise ValueError("Visual plan captions must be a list")
        self.plan = plan
        self.scenes = scenes
        self.captions = captions
        self.duration_ms = int(plan["duration_ms"])
        self._scene_starts = [int(scene["start_ms"]) for scene in scenes]
        self._caption_starts = [int(caption["start_ms"]) for caption in captions]
        self._validate()

    @classmethod
    def from_path(cls, path: str | Path) -> "PodcastSequencer":
        plan = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(plan)

    def at(
        self,
        playhead_ms: int | float,
        *,
        crossfade_ms: int | float | None = None,
    ) -> SequencerFrame:
        time_ms = max(0, min(int(playhead_ms), self.duration_ms))
        scene_index = self._index_at(self._scene_starts, time_ms, len(self.scenes))
        scene = self.scenes[scene_index]
        scene_start = int(scene["start_ms"])
        scene_end = int(scene["end_ms"])
        scene_duration = max(1, scene_end - scene_start)
        progress = max(0.0, min(1.0, (time_ms - scene_start) / scene_duration))
        loop_transition = self._loop_transition(
            scene_index,
            time_ms,
            crossfade_ms,
        )
        if loop_transition is not None:
            effective_crossfade_ms, crossfade_progress = loop_transition
            layers = self._loop_prompt_layers(crossfade_progress)
        else:
            effective_crossfade_ms = self._effective_crossfade_ms(
                scene_index,
                scene_duration,
                crossfade_ms,
            )
            elapsed = time_ms - scene_start
            crossfade_progress = (
                1.0
                if effective_crossfade_ms <= 0
                else max(0.0, min(1.0, elapsed / effective_crossfade_ms))
            )
            layers = self._prompt_layers(
                scene_index,
                time_ms,
                effective_crossfade_ms,
            )
        caption = self._caption_at(time_ms)
        return SequencerFrame(
            playhead_ms=time_ms,
            scene_id=str(scene["scene_id"]),
            scene_index=scene_index,
            scene_progress=progress,
            crossfade_ms=effective_crossfade_ms,
            crossfade_progress=crossfade_progress,
            caption_id=str(caption["caption_id"]) if caption else None,
            caption_speaker=str(caption.get("speaker", "")) if caption else "",
            caption_text=str(caption.get("text", "")) if caption else "",
            prompt_layers=tuple(layers),
        )

    def _effective_crossfade_ms(
        self,
        scene_index: int,
        scene_duration_ms: int,
        override_ms: int | float | None,
    ) -> int:
        if scene_index == 0:
            return 0
        scene = self.scenes[scene_index]
        requested = self._requested_crossfade_ms(
            override_ms,
            fallback=int(scene.get("crossfade_in_ms", 0)),
        )
        # Keep at least half of every visual scene at full strength. This also
        # prevents an overlong live-control value from crossing two boundaries
        # and introducing a discontinuity at the following scene.
        return min(requested, max(0, scene_duration_ms // 2))

    def _loop_transition(
        self,
        scene_index: int,
        time_ms: int,
        override_ms: int | float | None,
    ) -> tuple[int, float] | None:
        if len(self.scenes) < 2:
            return None
        fallback = int(self.plan.get("loop_crossfade_ms", 0))
        if fallback <= 0:
            fallback = next(
                (
                    int(scene.get("crossfade_in_ms", 0))
                    for scene in self.scenes[1:]
                    if int(scene.get("crossfade_in_ms", 0)) > 0
                ),
                0,
            )
        requested = self._requested_crossfade_ms(
            override_ms,
            fallback=fallback,
        )
        if requested <= 0:
            return None

        first_duration = int(self.scenes[0]["end_ms"]) - int(
            self.scenes[0]["start_ms"]
        )
        last_duration = int(self.scenes[-1]["end_ms"]) - int(
            self.scenes[-1]["start_ms"]
        )
        fade_ms = min(
            requested,
            max(0, first_duration),
            max(0, last_duration),
        )
        if fade_ms <= 0:
            return None

        before_boundary = fade_ms // 2
        after_boundary = fade_ms - before_boundary
        if (
            scene_index == len(self.scenes) - 1
            and time_ms >= self.duration_ms - before_boundary
        ):
            loop_progress = (
                time_ms - (self.duration_ms - before_boundary)
            ) / fade_ms
            return fade_ms, max(0.0, min(1.0, loop_progress))
        if scene_index == 0 and time_ms < after_boundary:
            loop_progress = (before_boundary + time_ms) / fade_ms
            return fade_ms, max(0.0, min(1.0, loop_progress))
        return None

    @staticmethod
    def _requested_crossfade_ms(
        override_ms: int | float | None,
        *,
        fallback: int,
    ) -> int:
        if override_ms is None:
            return max(0, int(fallback))
        return max(0, int(override_ms))

    def _prompt_layers(
        self,
        scene_index: int,
        time_ms: int,
        fade_ms: int,
    ) -> list[PromptLayer]:
        scene = self.scenes[scene_index]
        elapsed = time_ms - int(scene["start_ms"])
        if scene_index == 0 or fade_ms <= 0 or elapsed >= fade_ms:
            return self._scene_layers(scene, 1.0)
        amount = _smoothstep(elapsed / fade_ms)
        previous = self.scenes[scene_index - 1]
        return self._scene_layers(previous, 1.0 - amount) + self._scene_layers(
            scene, amount
        )

    def _loop_prompt_layers(self, progress: float) -> list[PromptLayer]:
        amount = _smoothstep(progress)
        return self._scene_layers(
            self.scenes[-1],
            1.0 - amount,
        ) + self._scene_layers(
            self.scenes[0],
            amount,
        )

    @staticmethod
    def _scene_layers(scene: dict[str, Any], weight: float) -> list[PromptLayer]:
        layers: list[PromptLayer] = []
        prompt = scene.get("prompt", {})
        chunks = prompt.get("chunks", [])
        seed = int(prompt.get("seed", 0))
        for chunk in chunks:
            text = str(chunk.get("text", "")).strip()
            if not text:
                continue
            layers.append(
                PromptLayer(
                    scene_id=str(scene["scene_id"]),
                    role=str(chunk.get("role", "narrative")),
                    text=text,
                    weight=max(0.0, float(chunk.get("weight", 1.0)) * weight),
                    seed=seed,
                )
            )
        return layers

    def _caption_at(self, time_ms: int) -> dict[str, Any] | None:
        if not self.captions:
            return None
        index = self._index_at(self._caption_starts, time_ms, len(self.captions))
        caption = self.captions[index]
        if int(caption["start_ms"]) <= time_ms < int(caption["end_ms"]):
            return caption
        return None

    @staticmethod
    def _index_at(starts: list[int], time_ms: int, length: int) -> int:
        return max(0, min(length - 1, bisect.bisect_right(starts, time_ms) - 1))

    def _validate(self) -> None:
        expected_start = 0
        for scene in self.scenes:
            start = int(scene["start_ms"])
            end = int(scene["end_ms"])
            if start != expected_start or end <= start:
                raise ValueError("Visual scenes must be positive and contiguous")
            expected_start = end
        if expected_start != self.duration_ms:
            raise ValueError("Visual scenes must cover the complete episode duration")


def _smoothstep(value: float) -> float:
    amount = max(0.0, min(1.0, value))
    return amount * amount * (3.0 - 2.0 * amount)
