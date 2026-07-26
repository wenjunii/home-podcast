from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
VISUALS_PATH = (
    ROOT
    / "episodes"
    / "2013-12.01"
    / "visuals"
    / "2013-12.01-visual-scenes.json"
)
RESULTS_PATH = (
    ROOT
    / "work"
    / "codex"
    / "visuals"
    / "2013-12.01-relevance-fixes.jsonl"
)
AUDIT_PATH = (
    ROOT
    / "work"
    / "qa"
    / "2013-12.01-visual-prompt-relevance-audit.json"
)


REPLACEMENTS: dict[str, dict[str, Any]] = {
    "visual-003": {
        "reason": "The OCR composition anticipated the following provenance passage.",
        "intent": "Keep the opening on the letter's painful change from home to visiting.",
        "prompt": (
            "Empty family-house threshold viewed from inside, a visitor's overnight "
            "bag and worn house key resting just beyond the open door, folded 1859 "
            "letter on a narrow hall table, no person visible, pale Cambridge winter "
            "light meeting warm amber interior, low 35mm composition, cinematic 4K "
            "documentary photography, quiet ache of realizing home has become somewhere "
            "one visits."
        ),
        "location_terms": ["cambridge"],
    },
    "visual-008": {
        "reason": "The Atlantic-window image did not represent the two-persona blog mystery.",
        "intent": "Make the single archived page shared by two literary personas visible.",
        "prompt": (
            "Oblique close-up of aging laptop showing one archived blog page split "
            "between two blurred author names and one post, no readable text, overlapping "
            "reflections share the dark screen, warm desk lamp against cool pixel light, "
            "scattered notes illegible, 50mm lens, cinematic 4K documentary photography, "
            "playful mystery of two literary personas occupying one digital room."
        ),
    },
    "visual-010": {
        "reason": "The old prompt illustrated the later truncation before the script reached it.",
        "intent": "Introduce the discovery of Beethoven's constrained travel through the scan.",
        "prompt": (
            "Open printed letter beneath cool scanner light, page numbers drifting "
            "across a nearby monitor as broken OCR, unopened travel trunk and folded "
            "countryside map fading into shadow beyond the desk, no person or readable "
            "text, warm candle amber meeting blue screen light, 50mm layered composition, "
            "cinematic 4K documentary photography, discovery of a life constrained before "
            "its journey begins."
        ),
    },
    "visual-015": {
        "reason": "Four letters inaccurately reduced four different kinds of archival voices.",
        "intent": "Represent the four voices through the different media that preserved them.",
        "prompt": (
            "Four archival traces arranged on one table—aged letter, laptop blog window, "
            "open grief journal, scanned book page—each ending at a different edge of "
            "light, no readable text, house key centered between them, warm amber and "
            "cool screen glow, overhead 50mm composition, cinematic 4K documentary "
            "photography, four voices reaching toward homes changed by time and distance."
        ),
    },
    "visual-018": {
        "reason": "Specific list objects appeared before the hosts actually named them.",
        "intent": "Introduce the expatriate list without revealing its punchline objects early.",
        "prompt": (
            "Open notebook on a Kenyan apartment table, five blank lines marked by small "
            "checkboxes beside a packed suitcase and laptop, no specific missed objects "
            "revealed yet, afternoon light crossing the page, anonymous hands just "
            "outside frame, muted ochre and blue palette, 50mm lens, cinematic 4K "
            "documentary photography, amused anticipation before an expatriate's intensely "
            "specific inventory of home."
        ),
        "location_terms": ["kenya"],
    },
    "visual-019": {
        "reason": "The England image belonged to the following commenter, not Emily's list.",
        "intent": "Show Emily's funny, specific inventory and the freedom attached to driving.",
        "prompt": (
            "Folded purple corduroy pants beside silver muffin tin, car keys and dark "
            "laptop on a Kenyan apartment table, 2012, objects arranged like affectionate "
            "inventory, warm late-afternoon light casting shadows over worn linen, no "
            "person visible, 50mm lens, cinematic 4K documentary photography, humor and "
            "homesickness held together with the freedom attached to driving."
        ),
        "location_terms": ["kenya"],
    },
    "visual-022": {
        "reason": "The honeysuckle detail was not doing the script's work about blurred roots.",
        "intent": "Hold sharp belonging and fading Midwestern detail inside a Brooklyn frame.",
        "prompt": (
            "Brooklyn apartment window framing dense city rooftops while a small "
            "handwritten Midwest road sketch fades beneath condensation on the sill, no "
            "readable text, one rooted houseplant leaning toward weak light, muted "
            "grey-green and ochre palette, shallow 50mm focus, cinematic 4K documentary "
            "photography, belonging still vivid while the details of home blur and loyalty "
            "becomes an obligation."
        ),
        "location_terms": ["brooklyn", "midwest"],
    },
    "visual-024": {
        "reason": "The garden walk illustrated source material outside the assigned passage.",
        "intent": "Make letters themselves carry remembrance across exile and distance.",
        "prompt": (
            "Sealed letters and loose flower petals form a fragile path across an "
            "unlabelled map between Germany and a small island, no readable text, edges "
            "held by smooth stones, soft May 1919 window light, overhead 50mm composition, "
            "faded rose, cream and sea-grey palette, cinematic 4K documentary photography, "
            "remembrance crossing distance while the writer remains unseen."
        ),
        "location_terms": ["german homeland", "the island"],
    },
    "visual-029": {
        "reason": "The kitchen and guitar anticipated a much later family confrontation.",
        "intent": "Show how digital archaeology located the republished homecoming essay.",
        "prompt": (
            "Open laptop and printed article proof on a passenger seat beside old road "
            "atlas, highway blurred beyond windshield, route bending toward Appalachia, "
            "no readable text or logos, cool screen light meeting late-autumn daylight, "
            "over-shoulder 35mm composition, cinematic 4K documentary photography, digital "
            "archaeology locating a first-person return through the television-site page "
            "that preserved it."
        ),
        "location_terms": ["honaker", "atlanta"],
    },
    "visual-030": {
        "reason": "The guitar was neither spoken here nor the focus of the driving passage.",
        "intent": "Place the return drive beside the father and daughter's parallel departures.",
        "prompt": (
            "View through car windshield from Atlanta toward Honaker, Virginia, "
            "Appalachian ridges rising beneath late-autumn clouds, driver's face outside "
            "frame, youthful departure echoed by an empty road in rear-view mirror, muted "
            "brown and blue-grey palette, 35mm documentary composition, cinematic 4K "
            "photography, homecoming shadowed by a father's wartime departure and two "
            "inherited scars."
        ),
        "location_terms": ["honaker", "atlanta"],
        "sensitivity": (
            "The composition acknowledges intergenerational war trauma without reenacting "
            "combat or inventing a face."
        ),
    },
    "visual-033": {
        "reason": "Food and a guitar over-specified a confrontation preserved only as text.",
        "intent": "Let the article's cutoff, closed door, and silent song carry the unresolved clash.",
        "prompt": (
            "Printed web article ending in a torn half-word on a parents' kitchen table, "
            "closed bedroom door and silent sheet music beyond, no instrument or readable "
            "text invented, untouched cup cooling in late-November window light, 85mm "
            "close focus, amber interior against blue shadow, cinematic 4K documentary "
            "photography, a family confrontation preserved only until the archive cuts "
            "away before resolution."
        ),
        "location_terms": ["parents' house", "honaker"],
        "sensitivity": (
            "The family conflict remains indirect and avoids inventing either person's face "
            "or reenacting trauma."
        ),
    },
    "visual-040": {
        "reason": "The old image blended Iowa farmland with a Texas courthouse into one place.",
        "intent": "Keep the Iowa and Texas hometown inventories visibly separate.",
        "prompt": (
            "Documentary diptych kept separate: empty lane in Mt. Union, Iowa, beside "
            "quiet Texas courthouse square, two anonymous walkers seen from behind taking "
            "inventory without crossing the central seam, late-May light, restrained earth "
            "palette, matched 35mm framing, cinematic 4K photography, two hometowns still "
            "on maps yet no longer belonging to their returning observers."
        ),
        "location_terms": ["mt. union", "courthouse square"],
    },
    "visual-041": {
        "reason": "The composition was relevant, but an unnecessary hair trait was foregrounded.",
        "intent": "Show three generations meeting family absence without unsupported portrait detail.",
        "prompt": (
            "Two adults seen only from behind stand in a rural Iowa cemetery, one safely "
            "holding an infant while fresh flowers rest beside family headstones, flat "
            "Henry County fields beneath a broad spring sky, no faces or unsupported "
            "physical traits, warm late-May sunlight, respectful 50mm documentary framing, "
            "cinematic 4K photography, three generations meeting the absence of two "
            "generations at once."
        ),
        "location_terms": ["mt. union", "henry county", "rural cemetery"],
        "identity_terms": [("age", "infant")],
    },
    "visual-045": {
        "reason": "The bowl of chili appeared well before the line that introduced it.",
        "intent": "Start with exact wages and prices rather than reveal the chili early.",
        "prompt": (
            "Scratched midcentury soda-fountain counter with worn service apron, stack of "
            "coins, napkin holder, saltine packets and ketchup bottle arranged beneath "
            "window light, no readable prices or faces, amber and faded mustard palette, "
            "close 50mm composition, cinematic 4K documentary photography, exact wages "
            "and tiny costs turning small-town nostalgia from a mood into a material daily "
            "economy."
        ),
        "location_terms": ["cafe", "courthouse"],
    },
    "visual-047": {
        "reason": "The Shawsheen River appeared before the next scene named it.",
        "intent": "Introduce the angry Andover return through the letter before its inventory.",
        "prompt": (
            "Folded letter to local editor rests on an Andover doorstep beside a town "
            "map, no readable text, returning man's coat and hands cropped at frame edge, "
            "overcast November 2012 light, ochre and slate palette, shallow 50mm focus, "
            "cinematic 4K documentary photography, anger gathering before he names the "
            "river, dams and school he believes the town has lost."
        ),
        "location_terms": ["andover"],
        "identity_terms": [("gender", "male")],
    },
    "visual-056": {
        "reason": "A polo patch anticipated the following false-nostalgia story.",
        "intent": "Summarize the four unsuccessful returns with evidence from those passages.",
        "prompt": (
            "Four places held in one tabletop composition: cemetery flowers, "
            "courthouse-square photograph, folded newspaper letter, and Christmas travel "
            "key beside an unlabelled map, no readable text or faces, late-afternoon amber "
            "across dark wood, overhead 50mm framing, cinematic 4K documentary photography, "
            "each object preserving a return that could not make its remembered home whole "
            "again."
        ),
    },
    "visual-057": {
        "reason": "The Atari object was not named in the script and arrived before the story.",
        "intent": "Keep the transition on generic smells, symbols, and objects.",
        "prompt": (
            "Unlabelled candle jar, faded toy box, worn house key and folded patterned "
            "cloth arranged on a tabletop, no logos or readable text, one empty space at "
            "center, warm scent-suggestive amber light, close 50mm composition, cinematic "
            "4K documentary photography, love displaced from vanished places into smells, "
            "symbols and ordinary objects, including things never personally owned."
        ),
    },
    "visual-058": {
        "reason": "The Otter Pop example appeared before the following scene named it.",
        "intent": "Introduce the blogger's physical reaction through anonymous consumer objects.",
        "prompt": (
            "Faded anonymous toy packaging and small plastic objects spread across orange "
            "shag carpet beside an open laptop, no logos, characters or readable text, one "
            "anonymous hand braced at the frame edge as if startled by memory, warm "
            "suburban afternoon through blinds, shallow 50mm focus, cinematic 4K "
            "documentary photography, forgotten consumer objects returning with the "
            "physical force described by their collector."
        ),
    },
    "visual-070": {
        "reason": "The schoolhouse alone did not carry the passage's missing perspective.",
        "intent": "Hold the remembered schoolhouse beside the perspective the settler account omits.",
        "prompt": (
            "Inside an empty frontier log schoolhouse, one unoccupied bench faces an "
            "oiled-paper window while the doorway frames a distant hollow stump and vacant "
            "trading place, no people depicted, neutral Indiana daylight, restrained timber "
            "and earth palette, deep 35mm composition, cinematic 4K documentary photography, "
            "remembered settler childhood held beside the Indigenous perspective the account "
            "does not preserve."
        ),
        "location_terms": ["whitewater", "log schoolhouse"],
        "sensitivity": (
            "No Indigenous person, threat imagery, or perspective absent from the source is "
            "invented."
        ),
    },
    "visual-083": {
        "reason": "The frost image anticipated the next passage's block of ice.",
        "intent": "Stay with the poem's repeated memories of being together.",
        "prompt": (
            "Two empty chairs pulled close beside a box of childhood keepsakes and a "
            "photograph turned face-down, no people or readable text, warm late-afternoon "
            "light touching both seats equally, shallow 50mm focus, muted amber and soft "
            "blue palette, cinematic 4K documentary photography, the poem's repeated "
            "memories keeping absent closeness present through the ritual of remembering "
            "together."
        ),
    },
    "visual-090": {
        "reason": "The swing repeated a park image more than four minutes after its passage.",
        "intent": "Close on partial web memory changing lost homes into other forms.",
        "prompt": (
            "Dark archive room at dawn, suspended fragments of a handwritten letter, poem "
            "page, blank design proof and ritual objects casting changing shapes across "
            "one wall, no people or readable text, warm light gradually entering cool blue "
            "shadow, wide 35mm composition, cinematic 4K documentary photography, the web's "
            "partial memory transforming lost homes into names, rituals, poems and "
            "unfinished correspondence."
        ),
    },
}


def _matches_any(value: str, terms: list[str]) -> bool:
    folded = value.casefold()
    return any(term.casefold() in folded for term in terms)


def _build_result(scene: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    grounding = scene.get("grounding", {})
    location_terms = list(spec.get("location_terms", []))
    locations = [
        dict(claim)
        for claim in grounding.get("locations", [])
        if _matches_any(str(claim.get("name", "")), location_terms)
    ]
    identity_terms = set(tuple(value) for value in spec.get("identity_terms", []))
    identities = [
        dict(claim)
        for claim in grounding.get("identity_claims", [])
        if (
            str(claim.get("attribute", "")),
            str(claim.get("value", "")),
        )
        in identity_terms
    ]
    sensitivity = spec.get(
        "sensitivity",
        "Faces and unsupported demographic traits remain outside frame.",
    )
    return {
        "scene_id": scene["scene_id"],
        "visual_intent": spec["intent"],
        "locations": locations,
        "identity_claims": identities,
        "unknown_identity_attributes": grounding.get(
            "unknown_identity_attributes",
            ["gender", "age", "race", "ethnicity", "nationality"],
        ),
        "camera_policy": (
            "Indirect documentary representation grounded in the assigned "
            "transcript; avoid invented faces and unsupported demographic traits."
        ),
        "prompt_chunks": [
            {
                "role": "narrative",
                "text": spec["prompt"],
                "weight": 1.0,
            }
        ],
        "seed": int(scene["prompt"]["seed"]),
        "sensitivity_notes": [sensitivity],
        "editorial_review_required": True,
    }


def build() -> dict[str, Any]:
    plan = json.loads(VISUALS_PATH.read_text(encoding="utf-8"))
    scenes = plan["scenes"]
    scene_by_id = {str(scene["scene_id"]): scene for scene in scenes}
    missing = sorted(set(REPLACEMENTS) - set(scene_by_id))
    if missing:
        raise ValueError(f"Replacement scenes are missing: {missing}")

    results = [
        _build_result(scene_by_id[scene_id], spec)
        for scene_id, spec in REPLACEMENTS.items()
    ]
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        "".join(
            json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n"
            for result in results
        ),
        encoding="utf-8",
    )

    reviews = []
    for scene in scenes:
        scene_id = str(scene["scene_id"])
        replacement = REPLACEMENTS.get(scene_id)
        reviews.append(
            {
                "scene_id": scene_id,
                "segment_ids": scene["segment_ids"],
                "decision": "replace" if replacement else "retain",
                "reason": (
                    replacement["reason"]
                    if replacement
                    else (
                        "Prompt directly represents a person, place, object, "
                        "archive action, or emotional concept in its assigned transcript."
                    )
                ),
            }
        )
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_PATH.write_text(
        json.dumps(
            {
                "episode_id": plan["episode_id"],
                "reviewed_against": (
                    "Every visual scene transcript and its assigned speech segments"
                ),
                "scene_count": len(scenes),
                "retained_count": len(scenes) - len(REPLACEMENTS),
                "replacement_count": len(REPLACEMENTS),
                "network_calls": 0,
                "scenes": reviews,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "episode_id": plan["episode_id"],
        "scenes_reviewed": len(scenes),
        "retained": len(scenes) - len(REPLACEMENTS),
        "replacements": len(REPLACEMENTS),
        "results": str(RESULTS_PATH),
        "audit": str(AUDIT_PATH),
        "network_calls": 0,
    }


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
