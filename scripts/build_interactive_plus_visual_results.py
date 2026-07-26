from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OLD_VISUALS = (
    ROOT
    / "episodes"
    / "2013-12.01"
    / "visuals"
    / "2013-12.01-visual-scenes-67-scene-pre-interactive-plus-backup.json"
)
NEW_VISUALS = (
    ROOT
    / "work"
    / "visuals"
    / "interactive-plus"
    / "2013-12.01-expanded-scenes.json"
)
JOBS_PATH = (
    ROOT
    / "work"
    / "visuals"
    / "interactive-plus"
    / "2013-12.01-prompt-jobs.jsonl"
)
OUTPUT_PATH = (
    ROOT
    / "work"
    / "codex"
    / "visuals"
    / "2013-12.01-interactive-plus-results.jsonl"
)


CUSTOM_PROMPTS: dict[str, dict[str, str]] = {
    "visual-001": {
        "intent": "Begin outside the letter: a student crosses the muddy threshold into Cambridge lodgings while carrying home in one small bag.",
        "prompt": (
            "Anonymous student seen from behind entering modest Cambridge lodgings "
            "in 1859, mud-streaked lane and melting snow behind him, small carpetbag "
            "in one hand and folded letter in the other, india-rubber boots catching "
            "pale afternoon light, muted sepia and slate palette, low doorway framing, "
            "cinematic 4K documentary photography, tender unease"
        ),
    },
    "visual-004": {
        "intent": "Show the letter's physical-to-digital passage as a tactile archaeological chain.",
        "prompt": (
            "Open nineteenth-century letter beneath a flatbed scanner lid, Cambridge "
            "date line visible only as blurred ink, book fibers and broken line spacing "
            "magnified in cold monitor reflections, worn india-rubber boot at frame edge, "
            "overhead composition, blue screen light meeting amber desk lamp, cinematic "
            "4K documentary photography, precise digital-archaeology atmosphere, no readable text"
        ),
    },
    "visual-006": {
        "intent": "Place saudade at the edge of departure through a suitcase and Atlantic horizon rather than an invented portrait.",
        "prompt": (
            "Weathered suitcase and volunteer notebook resting on dark volcanic ground "
            "above a Cape Verde shoreline, Atlantic horizon glowing violet and amber "
            "after sunset, an anonymous back-view figure already several steps away, "
            "wind lifting loose paper corners, restrained cobalt and rust palette, 35mm "
            "wide composition, cinematic 4K documentary photography, unresolved longing"
        ),
    },
    "visual-011": {
        "intent": "Visualize Beethoven's unreachable future through unused travel objects and an open landscape.",
        "prompt": (
            "Unused leather travel trunk beside polished walking boots in a quiet "
            "early-nineteenth-century room, open doorway revealing distant rolling "
            "countryside under luminous spring clouds, unfinished letter folded on the "
            "trunk, no person visible, warm interior amber against fresh green distance, "
            "medium-wide 35mm composition, cinematic 4K documentary photography, restrained aching possibility"
        ),
    },
    "visual-020": {
        "intent": "Turn the expatriate inventory into one rain-soaked domestic still life about mobility, sun, and ordinary comfort.",
        "prompt": (
            "Rain-beaded English window above a narrow sill holding car keys, a halved "
            "avocado, and one sleeve of a still-damp shirt, grey afternoon outside, "
            "faint warm reflection suggesting remembered Georgia sunlight, close 50mm "
            "composition, muted green and silver palette, shallow depth of field, cinematic "
            "4K documentary photography, affectionate humor without caricature"
        ),
    },
    "visual-025": {
        "intent": "Let the archival gap enter the island parsonage as a torn page among abundant signs of remembrance.",
        "prompt": (
            "Torn OCR printout ending in blank paper beside heaps of handwritten letters "
            "and cut flowers overflowing a narrow island parsonage table, lace curtain "
            "moving in soft May light, empty chair partly cropped, muted cream, faded rose, "
            "and sage palette, 85mm close composition, cinematic 4K documentary photography, "
            "careful uncertainty and remembered belonging"
        ),
    },
    "visual-031": {
        "intent": "Keep the return intimate and non-spectacular through the physical tension of driving into the mountains.",
        "prompt": (
            "Driver's hands gripping a worn steering wheel on a winding approach to "
            "Honaker Virginia, Appalachian ridges compressed through the windshield, "
            "late-autumn branches and low mist closing around the road, face kept outside "
            "frame, muted brown and blue-grey palette, shallow dashboard focus, cinematic "
            "4K documentary photography, guarded homecoming, trauma treated without spectacle"
        ),
    },
    "visual-034": {
        "intent": "Bridge the two Appalachian returns with a landscape whose quiet distance contains both memory and loss.",
        "prompt": (
            "High wide view into Smith Hollow near Abingdon Virginia, narrow road threading "
            "between wooded Appalachian slopes toward one weathered homeplace, late-afternoon "
            "haze softening the ridgelines, no people visible, bare branches mixed with "
            "persistent vines, restrained ochre and smoky blue palette, cinematic 4K "
            "documentary photography, calm transition from confrontation to quieter loss"
        ),
    },
    "visual-036": {
        "intent": "Hold childhood play against the physical decay of the grandparents' homeplace.",
        "prompt": (
            "Small weathered bicycle leaning against the broken porch of a Smith Hollow "
            "homeplace, woven hen-nest basket tucked beneath warped boards, vines entering "
            "a cracked window, one square of warm supper light imagined across the empty "
            "floor, low 50mm angle, muted Appalachian earth tones, cinematic 4K documentary "
            "photography, love persisting inside ruin"
        ),
    },
    "visual-042": {
        "intent": "Show remembered Henry County as a real town emptied of the relationships that once made it home.",
        "prompt": (
            "Empty lane at the edge of Mt. Union Iowa, modest houses and mature shade "
            "trees giving way to flat Henry County fields, late-May sunlight casting long "
            "shadows with no pedestrians present, a few fresh cemetery flowers on a car "
            "seat in foreground, 35mm documentary framing, cinematic 4K photography, "
            "warm landscape carrying unmistakable absence"
        ),
    },
    "visual-046": {
        "intent": "Make the vanished local economy tangible through groceries delivered by hand and an actual ice box.",
        "prompt": (
            "Brown paper grocery bag and glass milk bottle being placed inside an old "
            "wooden ice box in a small Texas home, narrow porch and courthouse-square "
            "street softly visible through the doorway, no logos or faces, warm late-afternoon "
            "amber, close 50mm lens, tactile wood and paper textures, cinematic 4K "
            "documentary photography, intimate economy of proximity"
        ),
    },
    "visual-049": {
        "intent": "Express the Andover dispute through damaged civic materials and divided spatial lines rather than endorsing one narrator.",
        "prompt": (
            "Broken school bricks and a weathered mill timber arranged beside the diminished "
            "Shawsheen River in Andover Massachusetts, two diverging footpaths entering "
            "opposite edges of frame, overcast November light, no people or readable signs, "
            "slate, rust, and dead-leaf palette, balanced wide composition, cinematic 4K "
            "documentary photography, civic memory held in unresolved tension"
        ),
    },
    "visual-055": {
        "intent": "Represent an inaccessible song through silent listening equipment and visibly incomplete fragments.",
        "prompt": (
            "Unpowered headphones beside a laptop whose lyric preview fades into a blank "
            "lower screen, waveform stopping abruptly, frosted window reflection obscuring "
            "the remaining lines, no readable text, cool blue-grey monitor glow against "
            "one warm desk lamp, 85mm close focus, cinematic 4K documentary photography, "
            "the strange silence of an archived song"
        ),
    },
    "visual-061": {
        "intent": "Visualize false nostalgia as a missing emblem inside genuine Florida sensory memory.",
        "prompt": (
            "Folded green polo shirt with an empty unstitched patch area on a sunlit Florida "
            "kitchen table, jalousie-window shadows crossing faded childhood ephemera and "
            "a glass of melting ice, no logo or readable branding, humid golden light, "
            "shallow 50mm focus, cinematic 4K documentary photography, playful yet uncanny "
            "memory for something never owned"
        ),
    },
    "visual-062": {
        "intent": "Show one blog post reached through two archival doorways without repeating the missing-image composition.",
        "prompt": (
            "Two overlapping browser windows mirrored across an aging laptop screen, each "
            "showing the same blurred article through different archive layouts, paired "
            "scroll positions and mismatched margins, no readable text or logos, warm desk "
            "lamp against cool pixel light, oblique over-shoulder angle, cinematic 4K "
            "documentary photography, methodical digital archaeology with gentle humor"
        ),
    },
    "visual-065": {
        "intent": "Frame Antrim as the threshold where family, ministry, and burial make the word home incomparable.",
        "prompt": (
            "View from inside a small nineteenth-century church doorway toward wooded Antrim "
            "hills and a quiet cemetery beyond, worn coat hanging near the threshold, "
            "folded anniversary letter on a plain bench, amber interior light meeting blue-grey "
            "evening, deep-focus 35mm composition, cinematic 4K documentary photography, "
            "reverent homecoming shaped by generations of memory"
        ),
    },
    "visual-069": {
        "intent": "Acknowledge the settler account's childhood fear while keeping the absent Indigenous perspective visibly unresolved.",
        "prompt": (
            "Large hollow stump at the edge of a nineteenth-century Whitewater Valley "
            "farm clearing, simple farmhouse distant through trees, empty trade table near "
            "the porch, no people depicted, low child's-eye camera without simulating danger, "
            "soft neutral daylight, restrained brown and green palette, cinematic 4K "
            "documentary photography, partial settler memory presented with deliberate absence"
        ),
    },
    "visual-072": {
        "intent": "Show the teacher making local land legible through study objects placed directly in the prairie.",
        "prompt": (
            "Weathered school desk set at the edge of the Red River Valley prairie, open "
            "mythology book beside a smooth local stone with no readable inscription, black "
            "loam furrows stretching beneath an enormous sky, late golden light, low wide-angle "
            "composition, cinematic 4K documentary photography, intellectual curiosity turning "
            "flat land into a place worth loving"
        ),
    },
    "visual-073": {
        "intent": "Connect an early hand-coded webpage to the Minnesota landscape it quietly preserved.",
        "prompt": (
            "Beige early-2000s computer glowing in a dark room, hand-coded webpage reduced "
            "to colored blocks with no readable text, small prairie photograph pinned beside "
            "the monitor, loose black soil in a shallow dish on the desk, cool screen light "
            "and amber lamp, cinematic 4K documentary photography, humble durable digital memory"
        ),
    },
    "visual-078": {
        "intent": "Translate a childhood park feeling into the first physical gestures of naming a future company.",
        "prompt": (
            "Scuffed leather baseball and short length of weathered swing chain arranged "
            "beside blank design proofs on a clean wooden worktable, Connecticut park trees "
            "softly reflected in the window, afternoon gold meeting cool office shadow, no "
            "readable brand text, overhead 50mm composition, cinematic 4K documentary photography, "
            "childhood feeling carried deliberately into adult work"
        ),
    },
    "visual-080": {
        "intent": "Treat the blogger's amateur semiotics as playful, affectionate close reading of ordinary objects.",
        "prompt": (
            "Magnifying glass hovering above faded 1980s toy packaging and a small blue "
            "plastic figure on a cluttered writing desk, handwritten arrows kept illegible, "
            "warm tungsten light, soft monitor glow, orange and teal palette, shallow macro "
            "focus, no logos or recognizable characters, cinematic 4K documentary photography, "
            "curious humor in taking pop culture seriously"
        ),
    },
    "visual-084": {
        "intent": "Turn the poem's emotional ice into a restrained physical barrier between two people without inventing their identities.",
        "prompt": (
            "Two anonymous hands resting on opposite sides of a frost-covered glass door, "
            "faces outside frame, faint beach dusk and long shoreline reflected behind them, "
            "ice crystals thickening through the center while warm amber survives at both "
            "edges, close 85mm composition, cinematic 4K documentary photography, tender "
            "distance between people who once shared everything"
        ),
    },
    "visual-089": {
        "intent": "Gather what the archive cannot restore into one carefully incomplete material constellation.",
        "prompt": (
            "Museum-like glass case holding a worn house key, candle stub, folded poem page, "
            "small baseball, and unfinished handwritten letter, each object separated by dark "
            "empty space, no readable text, narrow beam of late-afternoon light revealing dust "
            "and fingerprints, overhead 50mm composition, cinematic 4K documentary photography, "
            "evidence preserved while original lives remain unreachable"
        ),
    },
}


LOCATION_PREFERENCES = {
    "visual-001": "Cambridge",
    "visual-004": "Cambridge",
    "visual-006": "Cape Verde",
    "visual-011": "fatherland",
    "visual-020": "England",
    "visual-025": "parsonage",
    "visual-031": "Honaker",
    "visual-034": "Smith Hollow",
    "visual-036": "Smith Hollow",
    "visual-042": "Mt. Union",
    "visual-046": "courthouse square",
    "visual-049": "Andover",
    "visual-061": "Florida",
    "visual-065": "Antrim",
    "visual-069": "Whitewater valley",
    "visual-072": "Red River Valley",
    "visual-073": "Red River Valley",
    "visual-078": "PineRock Park",
    "visual-084": "beach",
}


CUSTOM_SENSITIVITY = {
    "visual-031": [
        "The source concerns intergenerational war trauma; framing stays with the journey and avoids reenactment."
    ],
    "visual-034": [
        "The image connects two nearby Appalachian stories only through supported regional landscape, not through invented people."
    ],
    "visual-069": [
        "The source is a settler account that omits the Indigenous traders' perspective; no Indigenous people or threat imagery are invented."
    ],
    "visual-084": [
        "The poem supplies no demographic identities, so only anonymous hands are shown and faces remain outside frame."
    ],
    "visual-089": [
        "The montage avoids reconstructing any unidentified person, traumatic event, or missing page."
    ],
}


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object in {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _matching_cost(
    old_scene: dict[str, Any],
    new_scene: dict[str, Any],
    *,
    scale: float,
    duration_ms: int,
) -> float:
    old_story_ids = set(old_scene["source_story_ids"])
    new_story_ids = set(new_scene["source_story_ids"])
    intersection = len(old_story_ids.intersection(new_story_ids))
    union = len(old_story_ids.union(new_story_ids)) or 1
    story_penalty = 1 - intersection / union
    no_overlap_penalty = 8 if not intersection else 0
    old_midpoint = (
        (int(old_scene["start_ms"]) + int(old_scene["end_ms"])) / 2
    ) * scale
    new_midpoint = (
        int(new_scene["start_ms"]) + int(new_scene["end_ms"])
    ) / 2
    timing_penalty = abs(old_midpoint - new_midpoint) / duration_ms * 4
    return no_overlap_penalty + story_penalty * 2 + timing_penalty


def _monotonic_mapping(
    old_scenes: list[dict[str, Any]],
    new_scenes: list[dict[str, Any]],
    *,
    old_duration_ms: int,
    new_duration_ms: int,
) -> dict[str, str]:
    old_count = len(old_scenes)
    new_count = len(new_scenes)
    infinity = float("inf")
    scale = new_duration_ms / old_duration_ms
    costs = [[infinity] * new_count for _ in range(old_count)]
    previous: list[list[int | None]] = [
        [None] * new_count for _ in range(old_count)
    ]
    for new_index in range(new_count - old_count + 1):
        costs[0][new_index] = _matching_cost(
            old_scenes[0],
            new_scenes[new_index],
            scale=scale,
            duration_ms=new_duration_ms,
        )
    for old_index in range(1, old_count):
        best_cost = infinity
        best_index: int | None = None
        upper = new_count - (old_count - old_index - 1)
        for new_index in range(old_index, upper):
            candidate_previous = new_index - 1
            if costs[old_index - 1][candidate_previous] < best_cost:
                best_cost = costs[old_index - 1][candidate_previous]
                best_index = candidate_previous
            costs[old_index][new_index] = best_cost + _matching_cost(
                old_scenes[old_index],
                new_scenes[new_index],
                scale=scale,
                duration_ms=new_duration_ms,
            )
            previous[old_index][new_index] = best_index
    new_index = min(
        range(old_count - 1, new_count),
        key=lambda index: costs[-1][index],
    )
    pairs: list[tuple[int, int]] = []
    for old_index in range(old_count - 1, -1, -1):
        pairs.append((old_index, new_index))
        if old_index:
            prior = previous[old_index][new_index]
            if prior is None:
                raise RuntimeError("Visual alignment failed")
            new_index = prior
    return {
        str(old_scenes[old_index]["scene_id"]): str(
            new_scenes[new_index]["scene_id"]
        )
        for old_index, new_index in reversed(pairs)
    }


def _apply_editorial_alignment(mapping: dict[str, str]) -> None:
    # Move compositions to the conversational beat they illustrate most
    # precisely, leaving the displaced scene for a new complementary prompt.
    mapping["visual-032"] = "visual-041"
    mapping["visual-048"] = "visual-063"
    mapping["visual-054"] = "visual-071"
    mapping["visual-058"] = "visual-077"
    mapping["visual-060"] = "visual-081"


def _claim_pools(
    old_scenes: list[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    locations: dict[str, list[dict[str, Any]]] = {}
    identities: dict[str, list[dict[str, Any]]] = {}
    for scene in old_scenes:
        grounding = scene.get("grounding", {})
        for claim in grounding.get("locations", []):
            story_id = str(claim.get("story_id", ""))
            if claim not in locations.setdefault(story_id, []):
                locations[story_id].append(claim)
        for claim in grounding.get("identity_claims", []):
            story_id = str(claim.get("story_id", ""))
            if claim not in identities.setdefault(story_id, []):
                identities[story_id].append(claim)
    return locations, identities


def _select_custom_locations(
    scene_id: str,
    job: dict[str, Any],
    location_pool: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    preference = LOCATION_PREFERENCES.get(scene_id)
    if preference is None:
        return []
    preference_folded = preference.casefold()
    candidates = [
        claim
        for story_id in job["source_story_ids"]
        for claim in location_pool.get(str(story_id), [])
        if preference_folded in str(claim.get("name", "")).casefold()
    ]
    return [dict(candidates[0])] if candidates else []


def _matched_result(
    old_scene: dict[str, Any],
    job: dict[str, Any],
    seed: int,
) -> dict[str, Any]:
    current_story_ids = set(str(value) for value in job["source_story_ids"])
    grounding = old_scene.get("grounding", {})
    prompt = old_scene["prompt"]
    return {
        "scene_id": job["scene_id"],
        "visual_intent": prompt["visual_intent"],
        "locations": [
            dict(claim)
            for claim in grounding.get("locations", [])
            if str(claim.get("story_id")) in current_story_ids
        ],
        "identity_claims": [
            dict(claim)
            for claim in grounding.get("identity_claims", [])
            if str(claim.get("story_id")) in current_story_ids
        ],
        "unknown_identity_attributes": grounding.get(
            "unknown_identity_attributes",
            ["gender", "age", "race", "ethnicity", "nationality"],
        ),
        "camera_policy": prompt["camera_policy"],
        "prompt_chunks": [
            {
                "role": "narrative",
                "text": prompt["chunks"][0]["text"],
                "weight": 1.0,
            }
        ],
        "seed": seed,
        "sensitivity_notes": prompt.get("sensitivity_notes", []),
        "editorial_review_required": True,
    }


def _custom_result(
    job: dict[str, Any],
    seed: int,
    location_pool: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    scene_id = str(job["scene_id"])
    spec = CUSTOM_PROMPTS[scene_id]
    base = spec["prompt"].strip()
    return {
        "scene_id": scene_id,
        "visual_intent": spec["intent"],
        "locations": _select_custom_locations(scene_id, job, location_pool),
        "identity_claims": [],
        "unknown_identity_attributes": [
            "gender",
            "age",
            "race",
            "ethnicity",
            "nationality",
        ],
        "camera_policy": (
            "Indirect documentary representation: use objects, landscape, "
            "back views, or tightly cropped hands; do not invent a face or "
            "unsupported demographic identity."
        ),
        "prompt_chunks": [
            {"role": "narrative", "text": base, "weight": 1.0},
            {
                "role": "narrative",
                "text": f"{base}. Fine natural grain",
                "weight": 1.0,
            },
            {
                "role": "narrative",
                "text": f"{base}. Fine natural grain, tactile detail",
                "weight": 1.0,
            },
        ],
        "seed": seed,
        "sensitivity_notes": CUSTOM_SENSITIVITY.get(
            scene_id,
            [
                "No unsupported face, demographic identity, readable text, logo, flag, or famous landmark is introduced."
            ],
        ),
        "editorial_review_required": True,
    }


def build() -> dict[str, Any]:
    old_plan = _load_object(OLD_VISUALS)
    new_plan = _load_object(NEW_VISUALS)
    jobs = _read_jsonl(JOBS_PATH)
    old_scenes = old_plan["scenes"]
    new_scenes = new_plan["scenes"]
    old_by_id = {str(scene["scene_id"]): scene for scene in old_scenes}
    job_by_id = {str(job["scene_id"]): job for job in jobs}
    seed_by_id = {
        str(scene["scene_id"]): int(scene["prompt"]["seed"])
        for scene in new_scenes
    }
    mapping = _monotonic_mapping(
        old_scenes,
        new_scenes,
        old_duration_ms=int(old_plan["duration_ms"]),
        new_duration_ms=int(new_plan["duration_ms"]),
    )
    _apply_editorial_alignment(mapping)
    new_to_old = {new_id: old_id for old_id, new_id in mapping.items()}
    if len(new_to_old) != len(mapping):
        raise ValueError("Editorial alignment assigned two old prompts to one scene")
    unmatched = [
        str(scene["scene_id"])
        for scene in new_scenes
        if str(scene["scene_id"]) not in new_to_old
    ]
    if set(unmatched) != set(CUSTOM_PROMPTS):
        raise ValueError(
            "Custom prompt set does not match unmatched scenes: "
            f"unmatched={unmatched}, custom={sorted(CUSTOM_PROMPTS)}"
        )

    location_pool, _ = _claim_pools(old_scenes)
    results: list[dict[str, Any]] = []
    for scene in new_scenes:
        scene_id = str(scene["scene_id"])
        job = job_by_id[scene_id]
        seed = seed_by_id[scene_id]
        old_id = new_to_old.get(scene_id)
        if old_id is not None:
            result = _matched_result(old_by_id[old_id], job, seed)
        else:
            result = _custom_result(job, seed, location_pool)
        results.append(result)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        "".join(
            json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n"
            for result in results
        ),
        encoding="utf-8",
    )
    return {
        "output": str(OUTPUT_PATH),
        "results": len(results),
        "preserved_unique_prompts": len(mapping),
        "new_complementary_prompts": len(unmatched),
        "custom_scene_ids": unmatched,
    }


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
