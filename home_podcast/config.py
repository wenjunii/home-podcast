from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProjectConfig:
    config_path: Path
    project_root: Path
    project_name: str
    primary_language: str
    exports_dir: Path
    catalog_path: Path
    themes_path: Path
    show_bible_path: Path
    voice_roster_path: Path
    episodes_dir: Path
    work_dir: Path
    audio_dir: Path
    target_stories_per_installment: int
    target_minutes_min: int
    target_minutes_max: int
    analysis_provider: dict[str, Any] | None
    script_provider: dict[str, Any] | None
    speech_provider: dict[str, Any] | None
    dialogue_provider: dict[str, Any] | None
    sound_effects_provider: dict[str, Any] | None
    visual_provider: dict[str, Any] | None = None

    @classmethod
    def load(cls, path: str | Path = "podcast.json") -> "ProjectConfig":
        config_path = Path(path).expanduser().resolve()
        data = json.loads(config_path.read_text(encoding="utf-8"))
        root = config_path.parent

        def resolve(value: str) -> Path:
            candidate = Path(value).expanduser()
            return candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()

        return cls(
            config_path=config_path,
            project_root=root,
            project_name=str(data["project_name"]),
            primary_language=str(data.get("primary_language", "en")),
            exports_dir=resolve(data["exports_dir"]),
            catalog_path=resolve(data.get("catalog_path", "data/catalog.sqlite3")),
            themes_path=resolve(data.get("themes_path", "config/themes.json")),
            show_bible_path=resolve(data.get("show_bible_path", "config/show_bible.json")),
            voice_roster_path=resolve(
                data.get("voice_roster_path", "config/voice_roster.json")
            ),
            episodes_dir=resolve(data.get("episodes_dir", "episodes")),
            work_dir=resolve(data.get("work_dir", "work")),
            audio_dir=resolve(data.get("audio_dir", "audio")),
            target_stories_per_installment=max(
                1, int(data.get("target_stories_per_installment", 30))
            ),
            target_minutes_min=int(data.get("target_minutes_min", 20)),
            target_minutes_max=int(data.get("target_minutes_max", 35)),
            analysis_provider=data.get("analysis_provider"),
            script_provider=data.get("script_provider"),
            speech_provider=data.get("speech_provider"),
            dialogue_provider=data.get("dialogue_provider"),
            sound_effects_provider=data.get("sound_effects_provider"),
            visual_provider=data.get("visual_provider") or data.get("script_provider"),
        )

    def load_themes(self) -> dict[str, Any]:
        return json.loads(self.themes_path.read_text(encoding="utf-8"))

    def load_show_bible(self) -> dict[str, Any]:
        return json.loads(self.show_bible_path.read_text(encoding="utf-8"))

    def load_voice_roster(self) -> dict[str, Any]:
        return json.loads(self.voice_roster_path.read_text(encoding="utf-8"))

    def ensure_runtime_directories(self) -> None:
        self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
        self.episodes_dir.mkdir(parents=True, exist_ok=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
