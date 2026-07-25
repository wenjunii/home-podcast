from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path
from typing import Any


EXPECTED_ROLES = ("curious_guide", "archive_nerd", "connector")


def create_episode_cast(
    roster_path: Path,
    episode_id: str,
    output_path: Path,
) -> tuple[dict[str, Any], bool]:
    if not episode_id.strip():
        raise ValueError("episode_id must be a non-empty string")
    roster = _load_object(roster_path)
    _validate_roster(roster)
    if output_path.exists():
        existing = _load_object(output_path)
        validate_episode_cast(existing, episode_id=episode_id)
        return existing, False

    seed_basis = f"episode-cast-v1:{episode_id}"
    role_by_id = {role["id"]: role for role in roster["roles"]}
    combinations = itertools.product(
        *(role_by_id[role_id]["candidates"] for role_id in EXPECTED_ROLES)
    )
    valid_combinations = [
        combination
        for combination in combinations
        if len({candidate["person_id"] for candidate in combination})
        == len(EXPECTED_ROLES)
        and len({candidate["voice_id"] for candidate in combination})
        == len(EXPECTED_ROLES)
    ]
    if not valid_combinations:
        raise ValueError("Voice roster has no valid three-person cast")
    maximum_accent_diversity = max(
        len({candidate["accent"] for candidate in combination})
        for combination in valid_combinations
    )
    accent_diverse_combinations = [
        combination
        for combination in valid_combinations
        if len({candidate["accent"] for candidate in combination})
        == maximum_accent_diversity
    ]

    def selection_key(combination: tuple[dict[str, Any], ...]) -> str:
        lineup = ":".join(candidate["person_id"] for candidate in combination)
        return hashlib.sha256(f"{seed_basis}:{lineup}".encode("utf-8")).hexdigest()

    selected_combination = min(
        accent_diverse_combinations,
        key=selection_key,
    )
    hosts = [
        {"id": role_id, **selected}
        for role_id, selected in zip(
            EXPECTED_ROLES,
            selected_combination,
            strict=True,
        )
    ]

    episode_cast = {
        "contract_version": 1,
        "episode_id": episode_id,
        "provider": roster["provider"],
        "selection": "deterministic_accent_aware_episode_rotation",
        "selection_seed_sha256": hashlib.sha256(
            seed_basis.encode("utf-8")
        ).hexdigest(),
        "accent_diversity": {
            "distinct_accents": maximum_accent_diversity,
            "accents": sorted({host["accent"] for host in hosts}),
        },
        "status": "selected",
        "hosts": hosts,
    }
    validate_episode_cast(episode_cast, episode_id=episode_id)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(episode_cast, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return episode_cast, True


def load_episode_cast(path: Path, *, episode_id: str | None = None) -> dict[str, Any]:
    episode_cast = _load_object(path)
    validate_episode_cast(episode_cast, episode_id=episode_id)
    return episode_cast


def validate_episode_cast(
    episode_cast: dict[str, Any],
    *,
    episode_id: str | None = None,
) -> None:
    if episode_cast.get("contract_version") != 1:
        raise ValueError("Episode cast contract_version must be 1")
    cast_episode_id = episode_cast.get("episode_id")
    if not isinstance(cast_episode_id, str) or not cast_episode_id.strip():
        raise ValueError("Episode cast requires an episode_id")
    if episode_id is not None and cast_episode_id != episode_id:
        raise ValueError(
            f"Episode cast belongs to {cast_episode_id!r}, not {episode_id!r}"
        )
    hosts = episode_cast.get("hosts")
    if not isinstance(hosts, list) or len(hosts) != len(EXPECTED_ROLES):
        raise ValueError("Episode cast must contain exactly three hosts")
    role_ids = [host.get("id") for host in hosts if isinstance(host, dict)]
    if sorted(role_ids) != sorted(EXPECTED_ROLES):
        raise ValueError(
            f"Episode cast roles must be {', '.join(EXPECTED_ROLES)}"
        )
    person_ids: set[str] = set()
    voice_ids: set[str] = set()
    display_names: set[str] = set()
    for host in hosts:
        for field in (
            "person_id",
            "display_name",
            "voice_name",
            "voice_id",
            "accent",
        ):
            if not isinstance(host.get(field), str) or not host[field].strip():
                raise ValueError(f"Episode cast host {host.get('id')!r} needs {field}")
        if host["person_id"] in person_ids:
            raise ValueError(f"Duplicate cast person_id {host['person_id']!r}")
        if host["voice_id"] in voice_ids:
            raise ValueError(f"Duplicate cast voice_id {host['voice_id']!r}")
        if host["display_name"].casefold() in display_names:
            raise ValueError(f"Duplicate display name {host['display_name']!r}")
        person_ids.add(host["person_id"])
        voice_ids.add(host["voice_id"])
        display_names.add(host["display_name"].casefold())


def _validate_roster(roster: dict[str, Any]) -> None:
    if roster.get("contract_version") != 1:
        raise ValueError("Voice roster contract_version must be 1")
    if not isinstance(roster.get("provider"), str) or not roster["provider"].strip():
        raise ValueError("Voice roster requires a provider")
    roles = roster.get("roles")
    if not isinstance(roles, list):
        raise ValueError("Voice roster roles must be an array")
    role_by_id = {
        role.get("id"): role for role in roles if isinstance(role, dict)
    }
    if sorted(role_by_id) != sorted(EXPECTED_ROLES):
        raise ValueError(
            f"Voice roster roles must be {', '.join(EXPECTED_ROLES)}"
        )
    people: dict[str, dict[str, str]] = {}
    voices: dict[str, dict[str, str]] = {}
    for role_id in EXPECTED_ROLES:
        candidates = role_by_id[role_id].get("candidates")
        if not isinstance(candidates, list) or len(candidates) < 2:
            raise ValueError(
                f"Voice roster role {role_id!r} needs at least two candidates"
            )
        for candidate in candidates:
            if not isinstance(candidate, dict):
                raise ValueError(f"Voice roster role {role_id!r} has an invalid candidate")
            for field in (
                "person_id",
                "display_name",
                "voice_name",
                "voice_id",
                "accent",
            ):
                if (
                    not isinstance(candidate.get(field), str)
                    or not candidate[field].strip()
                ):
                    raise ValueError(
                        f"Voice roster candidate for {role_id!r} needs {field}"
                    )
            identity = {
                field: candidate[field]
                for field in (
                    "person_id",
                    "display_name",
                    "voice_name",
                    "voice_id",
                    "accent",
                )
            }
            person_id = candidate["person_id"]
            voice_id = candidate["voice_id"]
            if person_id in people and people[person_id] != identity:
                raise ValueError(
                    f"Inconsistent roster person_id {person_id!r} across roles"
                )
            if voice_id in voices and voices[voice_id] != identity:
                raise ValueError(
                    f"Inconsistent roster voice_id {voice_id!r} across roles"
                )
            people[person_id] = identity
            voices[voice_id] = identity


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value
