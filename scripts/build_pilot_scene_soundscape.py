"""Build the continuous pilot soundscape from the approved 90-scene visual plan."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from home_podcast.scene_soundscape import build_scene_soundscape


EPISODE = ROOT / "episodes" / "2013-12.01"
VISUALS = EPISODE / "visuals" / "2013-12.01-visual-scenes.json"
TIMELINE = EPISODE / "audio" / "2013-12.01-timeline.json"
OUTPUT = EPISODE / "sound-design-scenes.json"
EXPECTED_VISUALS_SHA256 = (
    "da8375ad8e27abd13400de65b7af00e0e4d39d977e5c1d22958f48d30475e9d3"
)


def sound(
    description: str,
    transcript_label: str,
    *,
    gain_db: float = -30,
    mix_gain_db: float = 0,
) -> dict[str, object]:
    return {
        "sound_prompt": (
            "Seamless illustrative documentary ambience: "
            + description.strip().rstrip(".")
            + ". No voices, no speech, no singing, no music, no recognizable "
            "brand or operating-system sounds, no dramatic impacts; restrained "
            "natural dynamics and a stable texture designed to loop cleanly."
        ),
        "transcript_label": transcript_label,
        "gain_db": gain_db,
        "mix_gain_db": mix_gain_db,
    }


SOUND_PROMPTS = {
    "visual-001": sound(
        "a muddy Cambridge lane during thaw, light winter air, rubber boots crossing "
        "a low wooden threshold, a small carpetbag settling and folded letter paper",
        "muddy winter footsteps and a wooden lodging threshold",
    ),
    "visual-002": sound(
        "close paper fibers and one careful letter fold on a worn desk, faint dormitory "
        "room air, wet rubber boots settling near a cold window",
        "letter paper and a quiet dormitory room",
    ),
    "visual-003": sound(
        "an empty family-house hallway, open door moving slightly in winter air, a "
        "metal house key and overnight bag set gently beyond the threshold",
        "an open doorway, house key, and quiet hall",
        gain_db=-31,
    ),
    "visual-004": sound(
        "flatbed scanner carriage gliding under an old printed letter, delicate page "
        "fibers, low computer fan and sparse hard-drive ticks in a quiet workroom",
        "paper passing through a quiet scanner",
        gain_db=-29,
    ),
    "visual-005": sound(
        "fine rain against a window at dusk, faint interior air, envelopes and journal "
        "pages shifting beside a small house key",
        "rain on glass and soft paper movement",
        gain_db=-31,
    ),
    "visual-006": sound(
        "Atlantic shoreline wind over dark volcanic ground in Cape Verde, broad gentle "
        "surf, loose notebook pages and suitcase fabric moving in the breeze",
        "Atlantic surf, island wind, and loose pages",
        gain_db=-29,
    ),
    "visual-007": sound(
        "an aging laptop and low cooling fan on a wooden desk at night, tiny keyboard "
        "movements, paper notes and ceramic mug resonance in intimate stillness",
        "a quiet laptop, notes, and nighttime room tone",
    ),
    "visual-008": sound(
        "two overlapping archive windows suggested by paired soft digital flutters, "
        "an old screen hum, sparse disk activity and paper notes under a desk lamp",
        "paired archive-window flutters and an old screen hum",
    ),
    "visual-009": sound(
        "a solitary archived blog page at night, restrained computer fan, a blinking "
        "cursor suggested by one sparse electronic grain, handwritten notes moving",
        "a quiet archived blog page and handwritten notes",
        gain_db=-31,
    ),
    "visual-010": sound(
        "scanner light moving across an open printed letter, low mechanism glide, "
        "travel-trunk leather settling and a folded paper map in a shadowed room",
        "scanner mechanics, old paper, and a travel trunk",
    ),
    "visual-011": sound(
        "an unused leather trunk and polished walking boots in a quiet old room, open "
        "door admitting distant countryside wind and a letter edge lifting",
        "countryside air through an open door beside a travel trunk",
        gain_db=-31,
    ),
    "visual-012": sound(
        "warm countryside breeze entering a tall early nineteenth-century window, "
        "distant rolling-hill air, a letter page curling once on the worn sill and "
        "the stillness of an unfinished room",
        "open-window countryside air and an unfinished letter",
        gain_db=-32,
    ),
    "visual-013": sound(
        "an empty Wildomar house in dry late-afternoon California air, faint window "
        "breeze, floorboard settling, suspended dust and a small set of keys",
        "dry house air, settling floorboards, and keys",
        gain_db=-32,
    ),
    "visual-014": sound(
        "a laptop glowing in a dark room, low fan and sparse data texture ending "
        "abruptly, then returning to still room air and unfinished paper",
        "a quiet laptop fragment fading into unfinished stillness",
        gain_db=-32,
    ),
    "visual-015": sound(
        "layered old letter paper, scanned book fibers, a grief journal page and low "
        "laptop mechanisms arranged as one restrained archival worktable texture",
        "four layers of paper, book, journal, and computer",
    ),
    "visual-016": sound(
        "rain on a mid-nineteenth-century hotel window, close quill movement across "
        "paper, a wooden writing desk and low lamp-room air",
        "rain, quill on paper, and a quiet hotel room",
        gain_db=-31,
    ),
    "visual-017": sound(
        "the hushed aftermath of a grand hotel dinner, faint glass resonance, an ivory "
        "dice box touching linen and broad cool room air around an empty table",
        "faint glass and dice-box sounds in an empty dining room",
        gain_db=-31,
    ),
    "visual-018": sound(
        "a Kenyan apartment in afternoon air, suitcase cloth and zipper, notebook "
        "pages and five small pencil marks, with distant exterior breeze",
        "suitcase cloth, notebook pages, and apartment air",
    ),
    "visual-019": sound(
        "corduroy fabric, a silver muffin tin, car keys and a laptop resting on a linen "
        "table, playful small object textures with no rhythmic pattern",
        "corduroy, muffin tin, keys, and laptop textures",
        gain_db=-29,
    ),
    "visual-020": sound(
        "steady English rain on a narrow window, damp cloth, car keys, a kitchen board "
        "and muted grey afternoon room tone",
        "English rain, damp cloth, and kitchen-window air",
    ),
    "visual-021": sound(
        "warm wind moving through tall Midwestern grass beside a country road, distant "
        "tire hush and an immense open-sky ambience",
        "Midwestern grass wind and a distant road",
        gain_db=-29,
    ),
    "visual-022": sound(
        "muted Brooklyn rooftop and apartment ambience, distant traffic wash without "
        "horns, radiator breath, condensation and houseplant leaves at a window",
        "a muted Brooklyn apartment and distant city wash",
    ),
    "visual-023": sound(
        "spring island wind moving a lace curtain, abundant cut flowers, loose letters "
        "and soft parsonage floorboards near a distant shore",
        "island wind, flowers, letters, and a lace curtain",
    ),
    "visual-024": sound(
        "sealed letters and dry flower petals sliding lightly over an unlabelled paper "
        "map, quiet window air and distant rough sea",
        "letters and flower petals crossing a paper map",
        gain_db=-31,
    ),
    "visual-025": sound(
        "a torn OCR printout among handwritten letters and flowers, empty chair wood, "
        "lace curtain movement and a careful pause where the page ends",
        "torn paper, flowers, and an empty island room",
        gain_db=-27,
    ),
    "visual-026": sound(
        "open rolling country under soft overcast light, long wind through roadside "
        "grass and a distant walking rhythm absorbed into the landscape",
        "open-country wind along a distant road",
        gain_db=-29,
    ),
    "visual-027": sound(
        "hilltop twilight wind around a worn leather satchel and folded letter, grass "
        "moving above a quiet valley with wide desolate air",
        "hilltop wind, grass, and a leather satchel",
        gain_db=-31,
    ),
    "visual-028": sound(
        "soft dusk wind across a white dirt road, scattered wildflowers and long grass "
        "beneath a vast amber-violet sky",
        "dusk wind across a dirt road and wildflowers",
        gain_db=-30,
    ),
    "visual-029": sound(
        "steady highway interior wash, old road-atlas paper, restrained laptop fan and "
        "late-autumn air while a route bends toward Appalachia",
        "highway hush, road-atlas paper, and a laptop",
    ),
    "visual-030": sound(
        "car tires on a long road from Atlanta toward Appalachian ridges, subdued cabin "
        "air, late-autumn crosswind and distant mountain weather",
        "road and mountain air on an Appalachian return",
        gain_db=-29,
    ),
    "visual-031": sound(
        "tires following a tighter winding approach to Honaker Virginia, bare branches "
        "brushing in mist, guarded cabin air and restrained steering-wheel leather",
        "a winding Honaker road through mist and bare branches",
        gain_db=-31,
    ),
    "visual-032": sound(
        "a single car moving between steep Appalachian slopes, low tire wash, bare "
        "hardwoods and late-November wind held close by the mountains",
        "late-November road air enclosed by Appalachian mountains",
        gain_db=-31,
    ),
    "visual-033": sound(
        "a printed web article on a quiet kitchen table, paper ending sharply, a cup "
        "cooling, closed interior door and still house air after confrontation",
        "a quiet kitchen, cooling cup, and abruptly ending page",
        gain_db=-34,
    ),
    "visual-034": sound(
        "soft wind and distant woodland air passing through Smith Hollow near Abingdon, "
        "a narrow road and one weathered homeplace in late-afternoon haze",
        "woodland air moving through Smith Hollow",
        gain_db=-30,
    ),
    "visual-035": sound(
        "wind entering a ruined clapboard house through broken windows, kudzu leaves, "
        "rotting wood, a loose fence and one restrained structural creak",
        "wind, vines, and settling wood in a ruined homeplace",
        gain_db=-29,
    ),
    "visual-036": sound(
        "a bicycle wheel giving one faint metal tick beside warped porch boards, woven "
        "basket reeds, vines at a cracked window and warm empty-house air",
        "bicycle metal, porch boards, basket reeds, and vines",
        gain_db=-30,
    ),
    "visual-037": sound(
        "low CRT buzz and early-web computer fan in a dark room, a dusty desk and tiny "
        "pixel-like data grains with the feeling of a silent embedded player",
        "an old CRT, computer fan, and early-web data grains",
        gain_db=-30,
    ),
    "visual-038": sound(
        "boots on a rutted dirt road approaching a weathered Massachusetts farmhouse, "
        "autumn leaves, bare oak wind and distant fallow-field air",
        "autumn footsteps on a dirt road toward a farmhouse",
        gain_db=-30,
    ),
    "visual-039": sound(
        "quiet nineteenth-century New England lane, dry elm leaves, distant wooden "
        "building resonance and long late-afternoon wind around a returning walker",
        "dry leaves and wind along an old New England lane",
        gain_db=-30,
    ),
    "visual-040": sound(
        "two restrained hometown ambiences held apart: open Iowa field wind and the "
        "empty masonry hush of a Texas courthouse square, joined by neutral air",
        "Iowa field wind beside a quiet Texas courthouse square",
    ),
    "visual-041": sound(
        "gentle spring wind in a rural Iowa cemetery, flower paper and clothing fabric "
        "moving softly beneath a broad sky, with no spectacle",
        "spring cemetery wind and soft flower wrapping",
        gain_db=-34,
    ),
    "visual-042": sound(
        "late-May wind along an empty Mt. Union lane, mature shade trees, flat field "
        "grass and fresh flowers resting quietly inside a parked car",
        "late-May lane, field grass, and flowers in a quiet car",
        gain_db=-32,
    ),
    "visual-043": sound(
        "close newsprint fibers and a creased newspaper page on weathered wood, one "
        "small rustle reaching a torn edge and stopping into warm room air",
        "newsprint rustling to an abrupt torn edge",
        gain_db=-32,
    ),
    "visual-044": sound(
        "an empty small-town courthouse square in golden light, restrained footsteps, "
        "awning fabric, one distant storefront door and broad brick-street ambience",
        "footsteps and awnings around a quiet courthouse square",
        gain_db=-29,
    ),
    "visual-045": sound(
        "a scratched soda-fountain counter with small coin clinks, napkin paper, "
        "saltine packets, ketchup glass and a low room resonance",
        "coins, paper packets, and glass at an old soda counter",
        gain_db=-28,
    ),
    "visual-046": sound(
        "a brown grocery bag, glass milk bottle and wooden ice-box door in a small "
        "Texas home, with porch air and intimate household object resonance",
        "grocery paper, milk glass, and a wooden ice box",
        gain_db=-29,
    ),
    "visual-047": sound(
        "a folded letter on an Andover doorstep, overcast November wind, dry leaves, "
        "coat fabric and a town map opening before an argument",
        "November doorstep wind, a folded letter, and town map",
        gain_db=-30,
    ),
    "visual-048": sound(
        "dry autumn leaves scraping across the stone threshold of a repurposed New "
        "England civic building, cold exterior air and muted interior masonry hush",
        "dry leaves and stone-building resonance",
        gain_db=-30,
    ),
    "visual-049": sound(
        "the diminished Shawsheen River moving past broken brick and weathered mill "
        "timber, overcast wind and two quiet footpaths",
        "river water, mill timber, brick, and overcast wind",
        gain_db=-29,
    ),
    "visual-050": sound(
        "wind through flat stubble fields at a forked dirt road, a weathered signpost "
        "creaking once beneath an overcast Midwestern sky",
        "stubble-field wind and a creaking signpost",
        gain_db=-30,
    ),
    "visual-051": sound(
        "Christmas Eve rain on a childhood-bedroom window, quiet house heating, shelf "
        "objects and distant winter room tone around an occupied bed",
        "Christmas Eve rain and a quiet childhood bedroom",
        gain_db=-32,
    ),
    "visual-052": sound(
        "an aging LCD monitor and lyrics-aggregator page, low fan, dusty keyboard, "
        "fragmented loading texture and mismatched data fading before any song",
        "an aging monitor and fragmented lyric-page data",
        gain_db=-31,
    ),
    "visual-053": sound(
        "condensation on frosted glass, faint paper movement behind it, soft cold air "
        "and a sparse broken-encoding flutter that never becomes readable",
        "frosted glass, hidden paper, and broken digital texture",
        gain_db=-32,
    ),
    "visual-054": sound(
        "wind over newly scraped ground, exposed soil, uprooted stumps, loose dry debris "
        "and dust where hedgerows and wild trees once stood",
        "wind, dust, and loose debris across scraped ground",
        gain_db=-30,
    ),
    "visual-055": sound(
        "unpowered headphones beside a laptop, low fan and a faint waveform-like texture "
        "that breaks off, leaving clean quiet room air",
        "a digital waveform stopping beside silent headphones",
        gain_db=-33,
    ),
    "visual-056": sound(
        "cemetery flower paper, a courthouse photograph, folded newspaper, travel key "
        "and unlabelled map shifting lightly on one wooden table",
        "flowers, photograph, newspaper, key, and map on a table",
        gain_db=-25,
    ),
    "visual-057": sound(
        "an unlabelled candle jar, faded toy box, worn house key and patterned cloth in "
        "warm still room air, each object producing a sparse tactile texture",
        "candle jar, toy box, house key, and cloth",
        gain_db=-30,
    ),
    "visual-058": sound(
        "faded toy packaging, thin cardboard, small plastic objects and orange shag "
        "carpet beside a softly running laptop in suburban afternoon air",
        "toy cardboard, small plastic objects, and a laptop",
        gain_db=-29,
    ),
    "visual-059": sound(
        "a melting ice pop on a sun-heated green transformer box, tiny drips, metal heat "
        "hum, dry suburban air and distant skateboard wheels",
        "melting ice, hot metal hum, and distant skateboard wheels",
        gain_db=-28,
    ),
    "visual-060": sound(
        "sun-warmed magazine pages handled on a Florida kitchen table, humid afternoon "
        "insects beyond jalousie windows and soft louver movement in the breeze",
        "magazine pages, jalousie windows, and humid Florida air",
        gain_db=-29,
    ),
    "visual-061": sound(
        "folded polo fabric, faded childhood paper, a glass of melting ice and jalousie-"
        "window shadows in a warm humid Florida kitchen",
        "folded fabric, melting ice, and a humid Florida kitchen",
        gain_db=-26,
    ),
    "visual-062": sound(
        "two archive layouts on an aging laptop, paired scroll movements, mismatched "
        "digital margins, low fan and methodical soft interface flutters",
        "paired archive layouts scrolling on an aging laptop",
        gain_db=-30,
    ),
    "visual-063": sound(
        "old laptop screen hum, one broken-image data flutter, sparse hard-drive ticks "
        "and a truncated page collapsing into a few quiet digital grains",
        "a broken image, hard-drive ticks, and truncated data",
        gain_db=-31,
    ),
    "visual-064": sound(
        "old letter paper on an oak table near a farmhouse window, wooded-hill wind, "
        "soft overcast air and one dry page edge shifting against the wood",
        "old letter paper and wind from wooded hills",
        gain_db=-31,
    ),
    "visual-065": sound(
        "air moving through a small nineteenth-century church doorway, old bench wood, "
        "coat fabric and distant cemetery trees at blue-grey evening",
        "church doorway air, old bench wood, and distant trees",
        gain_db=-33,
    ),
    "visual-066": sound(
        "a weathered homestead at dusk, low hearth crackle, open-door wind, worn "
        "floorboards and distant hilltop cemetery air",
        "hearth, open-door wind, and old homestead floorboards",
        gain_db=-32,
    ),
    "visual-067": sound(
        "a clearly audible old-monitor electrical hum, steady cooling-fan airflow, "
        "crisp mechanical disk ticks and one brief dry scanner-page flutter suggesting "
        "a stray OCR header, all over a present archival-room air bed",
        "audible old-monitor hum, disk ticks, and an OCR interruption",
        gain_db=-24,
        mix_gain_db=6,
    ),
    "visual-068": sound(
        "yellowed county-history pages on a rough oak lectern, soft forest clearing air, "
        "page edges and wooden benches without any crowd sound",
        "county-history pages, oak lectern, and forest-clearing air",
        gain_db=-31,
    ),
    "visual-069": sound(
        "neutral wind through an empty nineteenth-century farm clearing, leaves around "
        "a hollow stump, distant farmhouse wood and an unused trade table",
        "wind, leaves, a hollow stump, and empty trade table",
        gain_db=-34,
    ),
    "visual-070": sound(
        "an empty frontier log schoolhouse, timber settling, oiled-paper window moving "
        "in Indiana daylight and soft outdoor air through the doorway",
        "settling log schoolhouse timber and an oiled-paper window",
        gain_db=-29,
    ),
    "visual-071": sound(
        "broad Red River Valley prairie wind across black-loam furrows and glowing wheat, "
        "a weathered schoolbook opening lightly on a fencepost",
        "prairie wind, wheat, soil, and a schoolbook",
        gain_db=-29,
    ),
    "visual-072": sound(
        "prairie wind around a weathered school desk, mythology-book pages and a smooth "
        "local stone beneath an enormous open sky",
        "prairie wind around a school desk, book, and stone",
        gain_db=-30,
    ),
    "visual-073": sound(
        "an early-2000s beige computer with gentle fan and hard-drive activity, hand-"
        "coded webpage data, prairie-window air and loose black soil on a desk",
        "an early computer, hand-coded page, prairie air, and soil",
        gain_db=-30,
    ),
    "visual-074": sound(
        "low CRT hum and dusty computer fan, a cursor-like electronic grain and a hand-"
        "coded page that cuts off into a clean digital dropout",
        "a CRT hum and hand-coded page ending abruptly",
        gain_db=-32,
    ),
    "visual-075": sound(
        "weathered archive paper, faded polo fabric and fine dust on a dark reading "
        "table, with one page edge and a quiet absence where an image should be",
        "archive paper, faded fabric, and quiet missing-image space",
        gain_db=-32,
    ),
    "visual-076": sound(
        "a company about-page on a quiet office computer, steady low fan, warm office "
        "room tone and distant park air entering through a partly open window while a "
        "baseball rests silently on the wooden desk",
        "office computer, quiet room tone, and distant park air",
        gain_db=-30,
    ),
    "visual-077": sound(
        "pine wind through an empty Connecticut park, giant swing rope and weathered "
        "chain moving gently beside a silent grass baseball diamond",
        "pine wind and a giant swing beside an empty ball field",
        gain_db=-28,
    ),
    "visual-078": sound(
        "a scuffed leather baseball, short weathered swing chain and blank design paper "
        "on a clean worktable, with reflected park trees in afternoon air",
        "baseball leather, swing chain, design paper, and park reflections",
        gain_db=-29,
    ),
    "visual-079": sound(
        "faded toy-package cardboard and plastic beside a softly running laptop, warm "
        "tungsten room air and a delicate dry curl of incense atmosphere",
        "toy cardboard, plastic, laptop fan, and warm room air",
        gain_db=-30,
    ),
    "visual-080": sound(
        "a magnifying glass moving above faded toy packaging and one small plastic "
        "figure, paper notes, wooden desk and gentle monitor hum",
        "magnifying glass, toy packaging, plastic, and monitor hum",
        gain_db=-29,
    ),
    "visual-081": sound(
        "quiet mall ventilation and warm retail-room air around shelves of ceramic "
        "Halloween candle holders, one delicate ceramic clink and soft display rustle",
        "mall air, ceramic candle holders, and seasonal display rustle",
        gain_db=-29,
    ),
    "visual-082": sound(
        "a laptop illuminating repeated poem lines, low fan, one cursor-like data grain "
        "and cyclical paper-soft digital texture in a dim room",
        "a laptop, repeating poem texture, and quiet cursor pulse",
        gain_db=-31,
    ),
    "visual-083": sound(
        "two empty chairs beside a keepsake box, old paper and a face-down photograph, "
        "soft floorboard settling and warm late-afternoon window air",
        "empty chairs, keepsake box, photograph, and settling floorboards",
        gain_db=-32,
    ),
    "visual-084": sound(
        "frost thickening across a glass door, fine ice crackle, cold air and distant "
        "beach-dusk waves held between two warm edges",
        "frosted glass, fine ice, cold air, and distant waves",
        gain_db=-32,
    ),
    "visual-085": sound(
        "an aged printed book beneath a flatbed scanner, gentle carriage motor, page "
        "fibers, glass resonance and a thin scan-line texture",
        "a printed book moving under a flatbed scanner",
        gain_db=-30,
    ),
    "visual-086": sound(
        "rain on wavy parlour glass, old wooden window frame, inward room air and an "
        "unsealed folded letter resting on a side table",
        "parlour rain, old window wood, and an unsealed letter",
        gain_db=-32,
    ),
    "visual-087": sound(
        "quill scratching softly across cream paper, then page printing, scanner "
        "carriage and sparse OCR data grains layered in a slow material transformation",
        "quill, printed page, scanner, and OCR layers",
        gain_db=-29,
    ),
    "visual-088": sound(
        "overlapping handwritten letters, poem paper and half-printed webpage on a "
        "weathered table, window air and floating dust in late-afternoon stillness",
        "letters, poem, webpage, window air, and dust",
        gain_db=-31,
    ),
    "visual-089": sound(
        "quiet museum-case air around a worn key, candle stub, paper, baseball and "
        "unfinished letter, subtle glass resonance and widely spaced object textures",
        "museum-case air around a key, candle, paper, baseball, and letter",
        gain_db=-25,
    ),
    "visual-090": sound(
        "a dark archive room gradually receiving dawn air, suspended paper fragments, "
        "small ritual objects, faint scanner mechanics and sparse warm digital dust",
        "dawn entering an archive room with paper and digital dust",
        gain_db=-31,
    ),
}


def main() -> None:
    report = build_scene_soundscape(
        VISUALS,
        TIMELINE,
        SOUND_PROMPTS,
        OUTPUT,
        expected_visuals_sha256=EXPECTED_VISUALS_SHA256,
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
