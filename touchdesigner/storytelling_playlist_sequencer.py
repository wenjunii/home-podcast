"""Offline multi-story clock. Never blend one person's memory into another's.

Loaded directly by TouchDesigner; no package installation or model imports.
"""
from __future__ import annotations

import bisect
import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "recovered_homes_playlist_base", Path(__file__).with_name("podcast_sequencer.py"))
_base = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _base
_spec.loader.exec_module(_base)


class PodcastSequencer(_base.PodcastSequencer):
    def __init__(self, plan):
        super().__init__(plan)
        self.stories = plan["playlist_stories"]
        self.story_starts = [int(s["start_ms"]) for s in self.stories]
        end = 0
        for story in self.stories:
            if story["start_ms"] != end or story["end_ms"] <= end:
                raise ValueError("Playlist stories must be contiguous")
            end = story["end_ms"]
        if end != self.duration_ms:
            raise ValueError("Stories must cover the complete playlist")
        self._story_start_set = set(self.story_starts)

    def story_index_at(self, time_ms):
        return max(0, min(len(self.stories)-1,
                          bisect.bisect_right(self.story_starts, int(time_ms))-1))

    def story_at(self, time_ms):
        return self.stories[self.story_index_at(time_ms)]

    def navigate(self, time_ms, delta, *, loop=True):
        index = self.story_index_at(time_ms) + int(delta)
        index = index % len(self.stories) if loop else max(0, min(len(self.stories)-1, index))
        return self.stories[index]["start_ms"]

    def _effective_crossfade_ms(self, scene_index, scene_duration_ms, override_ms):
        if int(self.scenes[scene_index]["start_ms"]) in self._story_start_set:
            return 0
        return super()._effective_crossfade_ms(scene_index, scene_duration_ms, override_ms)

    def _loop_transition(self, scene_index, time_ms, override_ms):
        # Loop and story joins fade through black, never preview future memories.
        return None

    def output_opacity_at(self, time_ms, fade_ms=None):
        story = self.story_at(time_ms)
        requested = self.plan.get("output_edge_fades", {}).get("default_ms", 1000)
        fade = max(0, min(float(requested if fade_ms is None else fade_ms),
                          (story["end_ms"]-story["start_ms"])/2))
        if fade == 0:
            return 1.0
        local = max(0, min(float(time_ms)-story["start_ms"],
                           story["end_ms"]-story["start_ms"]))
        amount = max(0, min(1, local/fade,
                            (story["end_ms"]-story["start_ms"]-local)/fade))
        return amount*amount*(3-2*amount)
