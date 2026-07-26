from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EPISODE_DIR = ROOT / "episodes" / "2013-12.01"
SOURCE_PATH = EPISODE_DIR / "script-pre-interactive-plus.json"
AUDITION_PATH = EPISODE_DIR / "interactive-plus-audition.json"
OUTPUT_PATH = EPISODE_DIR / "script.json"

HOSTS = ("curious_guide", "archive_nerd", "connector")
SKIP_AFTER_OPENING = {"m1-s002", "m1-s003", "m1-s011", "m1-s014"}

OPENING_ID_MAP = {
    0: "m1-s001",
    1: "m1-s002",
    2: "m1-s003",
    3: "m1-s003-b",
    4: "m1-s003-c",
    5: "m1-s003-d",
    6: "m1-s011",
    7: "m1-s011-b",
    8: "m1-s013",
    9: "m1-s013-b",
    10: "m1-s014",
    11: "m1-s014-b",
}

# These are editorial rewrites of unusually long explanatory sentences. Exact
# quotations are never rewritten.
SPECIAL_REWRITES: dict[str, list[dict[str, Any]]] = {
    "m1-s017": [
        {
            "speaker": "archive_nerd",
            "text": "The blog itself is a little mystery. The archive shows exactly one post.",
            "delivery": {"tone": "intrigued"},
        },
        {
            "speaker": "connector",
            "text": "It's called \"Raskalnikov\"—yes, Dostoevsky—but the display name is Saudade. Two literary personas are sharing one page.",
            "delivery": {"tone": "amused by the puzzle"},
        },
        {
            "speaker": "curious_guide",
            "text": "And the Cape Verdean Creole isn't translated for outsiders?",
            "delivery": {"audio_tags": ["cuts in"]},
        },
        {
            "speaker": "archive_nerd",
            "text": "No. That part of the page stays with the people who already understand it.",
            "delivery": {"tone": "warmly"},
        },
    ],
    "m1-s019": [
        {
            "speaker": "connector",
            "text": "Okay, now here's where Theo found something that floored me.",
            "delivery": {"tone": "energized"},
        },
        {
            "speaker": "curious_guide",
            "text": "In another OCR scan?",
            "delivery": {"tone": "guessing"},
        },
        {
            "speaker": "connector",
            "text": "Another scan, page numbers and all. And this one is a letter from Beethoven.",
            "delivery": {"tone": "revealing the surprise"},
        },
        {
            "speaker": "curious_guide",
            "text": "Wait. Beethoven?",
            "delivery": {"audio_tags": ["cuts in"]},
        },
    ],
    "m2-s005": [
        {
            "speaker": "archive_nerd",
            "text": "He pictures himself on a little island in the boundless ocean, surrounded by travelers gambling over champagne on a Sunday.",
            "delivery": {"tone": "painting the scene"},
        },
        {
            "speaker": "curious_guide",
            "text": "The Sunday champagne really bothered him.",
            "delivery": {"audio_tags": ["laughs"]},
        },
        {
            "speaker": "connector",
            "text": "He is also harsh about foreign faces and tongues in ways that are very much of his era. That's his period-bound lens, not ours.",
            "delivery": {"tone": "clear and matter-of-fact"},
        },
    ],
    "m2-s021": [
        {
            "speaker": "archive_nerd",
            "text": "And the essay quotes Goethe's Werther to make a devastating point.",
            "delivery": {"tone": "leaning in"},
        },
        {
            "speaker": "connector",
            "text": "When you finally reach the distance you wanted—when 'there' becomes 'here'—everything is afterwards as it was before.",
            "delivery": {"tone": "slowly, letting the reversal land"},
        },
        {
            "speaker": "curious_guide",
            "text": "So arrival can make the dream smaller?",
            "delivery": {"audio_tags": ["hesitates"]},
        },
        {
            "speaker": "archive_nerd",
            "text": "Exactly. You arrive, and the magic collapses.",
            "delivery": {"tone": "quietly"},
        },
    ],
    "m2-s022": [
        {
            "speaker": "curious_guide",
            "text": "Wheeler sighing for home voices. Kathleen gripping the steering wheel through flat fields.",
            "delivery": {"tone": "gathering the stories together"},
        },
        {
            "speaker": "connector",
            "text": "Emily dreaming of purple pants. The unnamed exile counting birthday flowers.",
            "delivery": {"tone": "warmly"},
        },
        {
            "speaker": "archive_nerd",
            "text": "They're all living inside that word: Sehnsucht.",
            "delivery": {"tone": "softly, with recognition"},
        },
    ],
    "m3-s005": [
        {
            "speaker": "connector",
            "text": "Her father came home with PTSD, and the family kept it secret for years.",
            "delivery": {"tone": "carefully"},
        },
        {
            "speaker": "curious_guide",
            "text": "She describes the secret growing inside her like a cancer—those are her words.",
            "delivery": {"tone": "quietly"},
        },
    ],
    "m3-s014": [
        {
            "speaker": "archive_nerd",
            "text": "And the page itself is kind of a rotting house.",
            "delivery": {"tone": "seeing the parallel"},
        },
        {
            "speaker": "curious_guide",
            "text": "A MIDI file?",
            "delivery": {"audio_tags": ["cuts in", "laughs"]},
        },
        {
            "speaker": "archive_nerd",
            "text": "Set to auto-play—a song called \"Old Home Place.\"",
            "delivery": {"audio_tags": ["laughs"]},
        },
        {
            "speaker": "connector",
            "text": "There's also a boilerplate lyrics disclaimer that doesn't apply to her original poem.",
            "delivery": {"tone": "amused"},
        },
        {
            "speaker": "curious_guide",
            "text": "The poem is dated 2009, but the memorial-site design feels older. The crawler found it in 2013.",
            "delivery": {"tone": "nostalgic"},
        },
        {
            "speaker": "archive_nerd",
            "text": "The old web had confidence.",
            "delivery": {"audio_tags": ["laughs"]},
        },
    ],
    "m4-s001": [
        {
            "speaker": "curious_guide",
            "text": "So we've talked about leaving and coming back. But here's what nobody warns you about.",
            "delivery": {"tone": "conspiratorial, then reflective"},
        },
        {
            "speaker": "connector",
            "text": "Sometimes the place is still on the map, still has a zip code, and it is just… not yours anymore.",
            "delivery": {"tone": "softly"},
        },
    ],
    "m5-s005": [
        {
            "speaker": "connector",
            "text": "His example is painfully specific: an Otter Pop, a hot green electrical transformer box, surf shorts, and a friend talking skateboarding.",
            "delivery": {"tone": "vividly"},
        },
        {
            "speaker": "archive_nerd",
            "text": "He can still feel that box burning through the fabric. That's not a concept. That's a full-body memory.",
            "delivery": {"audio_tags": ["laughs"]},
        },
    ],
    "m5-s012": [
        {
            "speaker": "connector",
            "text": "That same ache turns up across centuries.",
            "delivery": {"tone": "making the turn"},
        },
        {
            "speaker": "curious_guide",
            "text": "Right beside this blog post in the crawl is a letter from the eighteen hundreds.",
            "delivery": {"tone": "curious"},
        },
        {
            "speaker": "archive_nerd",
            "text": "Its writer is explaining to a reverend named Cochrane why he cannot attend the centennial of a town called Antrim.",
            "delivery": {"tone": "precise"},
        },
    ],
    "m5-s019": [
        {
            "speaker": "curious_guide",
            "text": "A Hancock County history gives us another voice from a similar commemorative book.",
            "delivery": {"tone": "setting up a discovery"},
        },
        {
            "speaker": "archive_nerd",
            "text": "Reverend William Nichols stands at an old settlers' meeting and says something that could be an instruction manual for this podcast.",
            "delivery": {"tone": "intrigued"},
        },
    ],
    "m5-s021": [
        {
            "speaker": "connector",
            "text": "Nichols was born before Indiana was even a state.",
            "delivery": {"tone": "measured"},
        },
        {
            "speaker": "archive_nerd",
            "text": "He remembers hiding in a hollow stump at age four because a party of Indigenous people came to his father's house to trade.",
            "delivery": {"tone": "carefully"},
        },
        {
            "speaker": "curious_guide",
            "text": "We need to mark the frame: this is a settler's account of that encounter.",
            "delivery": {"tone": "firmly"},
        },
        {
            "speaker": "connector",
            "text": "His childhood fear was real to him, but the story does not include the perspective of the people who were already there.",
            "delivery": {"tone": "carefully, without speculation"},
        },
    ],
    "m6-s013": [
        {
            "speaker": "curious_guide",
            "text": "Fragments keep being the theme. There's a poem on PoetrySoup by Andrew Nashat called \"Do you remember.\"",
            "delivery": {"tone": "gently"},
        },
        {
            "speaker": "connector",
            "text": "We only have a name on a community poetry site; we don't know more about the writer.",
            "delivery": {"tone": "carefully"},
        },
        {
            "speaker": "archive_nerd",
            "text": "The whole poem is built on that phrase, repeated like a heartbeat.",
            "delivery": {"tone": "quietly"},
        },
    ],
    "m6-s018": [
        {
            "speaker": "curious_guide",
            "text": "He's talking about Stephan von Breuning, a childhood friend who has come back into his life.",
            "delivery": {"tone": "warmly"},
        },
        {
            "speaker": "connector",
            "text": "Then he says he has to withdraw from everyone because of his hearing loss.",
            "delivery": {"audio_tags": ["sighs"]},
        },
        {
            "speaker": "archive_nerd",
            "text": "The people he most wants to reach are the very people he is being pulled away from.",
            "delivery": {"tone": "softly"},
        },
    ],
    "m6-s020": [
        {
            "speaker": "connector",
            "text": "Think about the layers between us and that voice. A hand writes a letter. An editor prints it.",
            "delivery": {"tone": "counting the transformations"},
        },
        {
            "speaker": "curious_guide",
            "text": "A scanner reads it. A crawler captures it.",
            "delivery": {"tone": "picking up the rhythm"},
        },
        {
            "speaker": "archive_nerd",
            "text": "Then we find it two hundred years later in a file called beethovensletter001beet underscore djvu dot txt.",
            "delivery": {"tone": "delighted by the absurd filename"},
        },
    ],
    "m6-s009": [
        {
            "speaker": "connector",
            "text": "He calls himself an amateur semiotician.",
            "delivery": {"tone": "setting up the joke"},
        },
        {
            "speaker": "curious_guide",
            "text": "On a blog about Smurfs.",
            "delivery": {"audio_tags": ["interrupting", "laughs"]},
        },
        {
            "speaker": "archive_nerd",
            "text": "Which is a wonderful sentence.",
            "delivery": {"audio_tags": ["laughs"]},
        },
    ],
}

INTERJECTIONS: dict[str, list[dict[str, Any]]] = {
    "m1-s008": [
        {
            "speaker": "connector",
            "text": "So December is the shelf date, not the birth date.",
            "delivery": {"tone": "clarifying"},
        }
    ],
    "m1-s023": [
        {
            "speaker": "connector",
            "text": "The silence belongs to the file, not necessarily to him.",
            "delivery": {"audio_tags": ["sighs"]},
        }
    ],
    "m1-s027": [
        {
            "speaker": "connector",
            "text": "Twice now, the archive has closed the door before the ending.",
            "delivery": {"audio_tags": ["exhales"]},
        }
    ],
    "m2-s007": [
        {
            "speaker": "curious_guide",
            "text": "How specific are we talking?",
            "delivery": {"audio_tags": ["cuts in"]},
        }
    ],
    "m2-s008": [
        {
            "speaker": "curious_guide",
            "text": "The muffin tin is the one that gets me.",
            "delivery": {"audio_tags": ["laughs"]},
        }
    ],
    "m2-s010": [
        {
            "speaker": "archive_nerd",
            "text": "Honestly? Avocados can do that.",
            "delivery": {"audio_tags": ["laughs"]},
        }
    ],
    "m2-s018": [
        {
            "speaker": "connector",
            "text": "A gap is not permission to invent.",
            "delivery": {"tone": "firmly"},
        }
    ],
    "m3-s004": [
        {
            "speaker": "archive_nerd",
            "text": "Both scarred by his war. That line just sits there.",
            "delivery": {"audio_tags": ["exhales"]},
        }
    ],
    "m3-s018": [
        {
            "speaker": "connector",
            "text": "Homecoming as time travel.",
            "delivery": {"tone": "quietly connecting the stories"},
        }
    ],
    "m4-s010": [
        {
            "speaker": "curious_guide",
            "text": "Print sixty-seven?",
            "delivery": {"audio_tags": ["interrupting", "laughs"]},
        },
        {
            "speaker": "archive_nerd",
            "text": "The machine thought the counter was prose.",
            "delivery": {"audio_tags": ["laughs"]},
        },
    ],
    "m4-s011": [
        {
            "speaker": "connector",
            "text": "A soda skeet?",
            "delivery": {"audio_tags": ["cuts in"]},
        }
    ],
    "m4-s012": [
        {
            "speaker": "archive_nerd",
            "text": "A dime, plus structural crackers.",
            "delivery": {"audio_tags": ["laughs"]},
        }
    ],
    "m4-s013": [
        {
            "speaker": "curious_guide",
            "text": "And an actual ice box.",
            "delivery": {"audio_tags": ["laughs"]},
        }
    ],
    "m4-s017": [
        {
            "speaker": "archive_nerd",
            "text": "The person who stayed might answer very differently.",
            "delivery": {"audio_tags": ["hesitates"]},
        }
    ],
    "m4-s023": [
        {
            "speaker": "curious_guide",
            "text": "Frosted glass is exactly it.",
            "delivery": {"audio_tags": ["exhales"]},
        }
    ],
    "m5-s006": [
        {
            "speaker": "connector",
            "text": "Wait—nostalgia for a shirt he never owned?",
            "delivery": {"audio_tags": ["cuts in"]},
        }
    ],
    "m5-s010": [
        {
            "speaker": "curious_guide",
            "text": "The missing image is the thing doing all the work.",
            "delivery": {"tone": "marveling"},
        }
    ],
    "m5-s017": [
        {
            "speaker": "connector",
            "text": "A page header just walked into somebody else's letter.",
            "delivery": {"audio_tags": ["laughs"]},
        }
    ],
    "m5-s021": [
        {
            "speaker": "curious_guide",
            "text": "And that missing perspective matters as much as the remembered fear.",
            "delivery": {"tone": "firmly"},
        }
    ],
    "m5-s029": [
        {
            "speaker": "connector",
            "text": "Again?",
            "delivery": {"audio_tags": ["sighs"]},
        }
    ],
    "m6-s002": [
        {
            "speaker": "connector",
            "text": "He named the future after the feeling.",
            "delivery": {"tone": "quietly moved"},
        }
    ],
    "m6-s010": [
        {
            "speaker": "archive_nerd",
            "text": "And there goes the sentence again.",
            "delivery": {"audio_tags": ["sighs"]},
        }
    ],
    "m6-s014": [
        {
            "speaker": "archive_nerd",
            "text": "That repetition sounds like someone trying to keep a door open.",
            "delivery": {"audio_tags": ["exhales"]},
        }
    ],
    "m6-s020": [
        {
            "speaker": "curious_guide",
            "text": "That filename is practically sediment.",
            "delivery": {"audio_tags": ["laughs"]},
        }
    ],
}

TAG_NORMALIZATION = {
    "chuckles": "laughs",
    "exhales softly": "exhales",
    "sighs softly": "sighs",
}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected an object in {path}")
    return value


def _split_sentences(text: str) -> list[str]:
    return [
        part.strip()
        for part in re.split(r'(?<=[.!?])\s+(?=[A-Z“"])', text)
        if part.strip()
    ]


def _group_sentences(text: str, maximum_words: int = 28) -> list[str]:
    grouped: list[str] = []
    for sentence in _split_sentences(text):
        candidate = f"{grouped[-1]} {sentence}" if grouped else sentence
        if grouped and len(candidate.split()) <= maximum_words:
            grouped[-1] = candidate
        else:
            grouped.append(sentence)
    return grouped or [text]


def _suffix(index: int) -> str:
    if index == 0:
        return ""
    return f"-{chr(ord('a') + index)}"


def _normalize_delivery(value: Any) -> dict[str, Any]:
    delivery = copy.deepcopy(value) if isinstance(value, dict) else {}
    tags = delivery.get("audio_tags")
    if isinstance(tags, list):
        delivery["audio_tags"] = [
            TAG_NORMALIZATION.get(str(tag).strip().casefold(), str(tag).strip())
            for tag in tags
            if str(tag).strip()
        ]
    return delivery


def _parts_for_segment(segment: dict[str, Any]) -> list[dict[str, Any]]:
    segment_id = str(segment["segment_id"])
    if segment_id in SPECIAL_REWRITES:
        parts = copy.deepcopy(SPECIAL_REWRITES[segment_id])
    elif segment.get("kind") == "quote":
        parts = [
            {
                "speaker": segment["speaker"],
                "text": segment["text"],
                "delivery": _normalize_delivery(segment.get("delivery")),
            }
        ]
    else:
        texts = _group_sentences(str(segment["text"]))
        start = HOSTS.index(str(segment["speaker"]))
        parts = []
        for index, text in enumerate(texts):
            delivery = (
                _normalize_delivery(segment.get("delivery")) if index == 0 else {}
            )
            parts.append(
                {
                    "speaker": HOSTS[(start + index) % len(HOSTS)],
                    "text": text,
                    "delivery": delivery,
                }
            )

    output: list[dict[str, Any]] = []
    for index, part in enumerate(parts):
        new_segment = {
            "segment_id": f"{segment_id}{_suffix(index)}",
            "speaker": part["speaker"],
            "kind": segment.get("kind", "host_dialogue")
            if segment_id not in SPECIAL_REWRITES
            else "host_dialogue",
            "text": part["text"],
            "source_story_ids": copy.deepcopy(segment.get("source_story_ids", [])),
            "delivery": _normalize_delivery(part.get("delivery")),
            "pronunciation": copy.deepcopy(segment.get("pronunciation", {})),
            "pause_after_ms": 0,
        }
        output.append(new_segment)
    output[-1]["pause_after_ms"] = int(segment.get("pause_after_ms", 0))
    return output


def _interjections_after(segment: dict[str, Any]) -> list[dict[str, Any]]:
    original_id = str(segment["segment_id"])
    specs = INTERJECTIONS.get(original_id, [])
    output: list[dict[str, Any]] = []
    for index, spec in enumerate(specs, start=1):
        output.append(
            {
                "segment_id": f"{original_id}-r{index}",
                "speaker": spec["speaker"],
                "kind": "host_dialogue",
                "text": spec["text"],
                "source_story_ids": copy.deepcopy(
                    spec.get("source_story_ids", segment.get("source_story_ids", []))
                ),
                "delivery": _normalize_delivery(spec.get("delivery")),
                "pronunciation": copy.deepcopy(spec.get("pronunciation", {})),
                "pause_after_ms": 0,
            }
        )
    if output:
        output[-1]["pause_after_ms"] = int(segment.get("pause_after_ms", 0))
    return output


def _audition_segments(
    audition: dict[str, Any], indexes: range
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for index in indexes:
        segment = copy.deepcopy(audition["segments"][index])
        segment["segment_id"] = OPENING_ID_MAP[index]
        if index == 8:
            segment["text"] = (
                "A century and a half later, a blogger chooses the name "
                "Saudade—a word for longing that never quite resolves."
            )
        segment["pause_after_ms"] = int(segment.get("pause_after_ms", 0))
        segment["delivery"] = _normalize_delivery(segment.get("delivery"))
        output.append(segment)
    return output


def build() -> dict[str, Any]:
    source = _load(SOURCE_PATH)
    audition = _load(AUDITION_PATH)
    output_segments: list[dict[str, Any]] = []

    for segment in source["segments"]:
        segment_id = str(segment["segment_id"])
        if segment_id == "m1-s001":
            output_segments.extend(_audition_segments(audition, range(0, 8)))
            continue
        if segment_id in SKIP_AFTER_OPENING:
            continue
        if segment_id == "m1-s013":
            output_segments.extend(_audition_segments(audition, range(8, 12)))
            continue

        parts = _parts_for_segment(segment)
        reactions = _interjections_after(segment)
        if reactions:
            parts[-1]["pause_after_ms"] = 0
        output_segments.extend(parts)
        output_segments.extend(reactions)

    result = {
        "contract_version": 1,
        "episode_id": source["episode_id"],
        "title": source["title"],
        "performance_style": "interactive-plus",
        "segments": output_segments,
    }
    OUTPUT_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


if __name__ == "__main__":
    script = build()
    reaction_tags = sum(
        len(segment.get("delivery", {}).get("audio_tags", []))
        for segment in script["segments"]
    )
    words = [len(segment["text"].split()) for segment in script["segments"]]
    print(
        json.dumps(
            {
                "output": str(OUTPUT_PATH),
                "segments": len(script["segments"]),
                "words": sum(words),
                "median_words_per_turn": sorted(words)[len(words) // 2],
                "max_words_per_turn": max(words),
                "explicit_audio_tags": reaction_tags,
            },
            indent=2,
        )
    )
