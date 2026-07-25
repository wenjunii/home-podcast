from __future__ import annotations

import hashlib
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
    hosts = []
    for role_id in EXPECTED_ROLES:
        candidates = role_by_id[role_id]["candidates"]
        digest = hashlib.sha256(
            f"{seed_basis}:{role_id}".encode("utf-8")
        ).digest()
        selected = candidates[int.from_bytes(digest[:8], "big") % len(candidates)]
        hosts.append({"id": role_id, **selected})

    episode_cast = {
        "contract_version": 1,
        "episode_id": episode_id,
        "provider": roster["provider"],
        "selection": "deterministic_episode_rotation",
        "selection_seed_sha256": hashlib.sha256(
            seed_basis.encode("utf-8")
        ).hexdigest(),
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
        for field in ("person_id", "display_name", "voice_name", "voice_id"):
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
    all_people: set[str] = set()
    all_voices: set[str] = set()
    for role_id in EXPECTED_ROLES:
        candidates = role_by_id[role_id].get("candidates")
        if not isinstance(candidates, list) or len(candidates) < 2:
            raise ValueError(
                f"Voice roster role {role_id!r} needs at least two candidates"
            )
        for candidate in candidates:
            if not isinstance(candidate, dict):
                raise ValueError(f"Voice roster role {role_id!r} has an invalid candidate")
            for field in ("person_id", "display_name", "voice_name", "voice_id"):
                if (
                    not isinstance(candidate.get(field), str)
                    or not candidate[field].strip()
                ):
                    raise ValueError(
                        f"Voice roster candidate for {role_id!r} needs {field}"
                    )
            if candidate["person_id"] in all_people:
                raise ValueError(
                    f"Duplicate roster person_id {candidate['person_id']!r}"
                )
            if candidate["voice_id"] in all_voices:
                raise ValueError(
                    f"Duplicate roster voice_id {candidate['voice_id']!r}"
                )
            all_people.add(candidate["person_id"])
            all_voices.add(candidate["voice_id"])


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value
