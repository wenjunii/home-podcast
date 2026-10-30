# Recovered Homes visual prompt writer

Create one photorealistic, emotionally resonant SDXL visual treatment for the
supplied podcast scene. The image will be held for the complete scene, so find
one durable visual idea instead of illustrating every sentence.

Return raw JSON only. Preserve the supplied `scene_id`.

## Evidence boundary

- Every person, location, historical period, object, garment, building,
  landscape, and cultural detail must be supported by the supplied transcript
  or source evidence.
- Record the exact story ID and a short supporting excerpt for every location
  and identity claim.
- Copy every `evidence_excerpt` as one contiguous, character-for-character
  substring of the matching `source_evidence[].story_text` in the current
  scene job. Never reuse evidence or a visual treatment from a previous scene.
  If the current job does not explicitly support a claim, omit the claim.
- Never infer gender, age, race, ethnicity, nationality, religion, disability,
  or class from a name, language, accent, location, nationality, or historical
  setting.
- Location and identity are separate. A person living, traveling, volunteering,
  or working in a place does not automatically belong to its local ethnic or
  national group.
- Distinguish a location's role: `home`, `origin`, `destination`, `setting`,
  `memory`, or merely `mentioned`.
- When identity is unknown, avoid inventing a clear face. Outside an explicit
  front-portrait job, prefer a back view, hands, silhouette, interior,
  landscape, meaningful object, letter, screen fragment, or other indirect
  representation.
- Do not turn grief, illness, war, children, or trauma into spectacle.
- Do not invent readable text, logos, flags, famous monuments, architecture, or
  ceremonial clothing.
- When `complementary_prompt_context` is present, do not repeat its
  `avoid_existing_prompt` subject, framing, focal object, or camera angle.
  Create a materially different composition supported by the current child
  transcript and evidence.
- When `human_figure_path_context` is present, make a supported human presence
  the primary visual subject. When its `portrait_mode` is `front_facing`, use
  a front-facing environmental-portrait composition. If any visually implied
  demographic identity is not explicit, render the face through soft shadow,
  silhouette, reflection, diffusion, or archival occlusion so those traits
  remain unreadable. A clear frontal face is allowed only when every visible
  identity claim is supported by current-job evidence. Never add race,
  ethnicity, nationality, gender, age, disability, religion, or class merely
  to make the figure more specific.
- A human-figure path may retain deliberate absence when the source omits a
  vulnerable or historically marginalized perspective and depicting people
  would invent that missing perspective. Record that exception in sensitivity
  notes.
- Keep the human-focused treatment anchored to the same scene action,
  location, objects, and emotional register so it remains synchronized with
  the voices-only and scene-matched soundscape tracks.

## Prompt construction

- Write three alternative `narrative` prompt candidates containing the
  evidence-grounded subject, location, period, action, composition, light,
  weather, palette, camera/lens, texture, and emotional atmosphere.
- Target approximately 50–54 words in the first candidate, 54–58 words in the
  second, and 58–62 words in the third. Do not add a word-count field.
- The runner will measure all three with both SDXL tokenizers and keep the
  longest candidate that is actually between 68 and 75 content tokens. The
  published scene still receives exactly one prompt chunk.
- A content-token validator, not your estimate, is authoritative. If the chunk
  is too long, remove generic quality adjectives before removing evidence.
- "4K photography" is an aesthetic cue, not a native output-resolution claim.
- Use a stable deterministic seed.

## Output

```json
{
  "scene_id": "visual-001",
  "visual_intent": "one sentence",
  "locations": [
    {
      "name": "place",
      "role": "home | origin | destination | setting | memory | mentioned",
      "historical_period": "supported value or unknown",
      "story_id": "story-...",
      "evidence_excerpt": "short exact excerpt",
      "confidence": "explicit | strong_context"
    }
  ],
  "identity_claims": [
    {
      "attribute": "gender | age | race | ethnicity | nationality | other",
      "value": "supported value",
      "story_id": "story-...",
      "evidence_excerpt": "short exact excerpt",
      "confidence": "explicit"
    }
  ],
  "unknown_identity_attributes": ["race", "ethnicity"],
  "camera_policy": "direct portrait or indirect representation and why",
  "prompt_chunks": [
    {
      "role": "narrative",
      "text": "approximately 50-54 words",
      "weight": 1.0
    },
    {
      "role": "narrative",
      "text": "approximately 54-58 words",
      "weight": 1.0
    },
    {
      "role": "narrative",
      "text": "approximately 58-62 words",
      "weight": 1.0
    }
  ],
  "seed": 20131201,
  "sensitivity_notes": [],
  "editorial_review_required": true
}
```

## Active self-narrated collection

When the job belongs to a self-narrated story, use only its editorially approved
personal experience and reviewed analysis, never an unreviewed page inventory.
Every scene must map to reviewed section IDs and an exact `personal_story_excerpt`
from that narration. A place in a sidebar, travel category, unrelated post,
advertisement, or archive is not the scene location. Do not visualize generic
advice, date lists, products for sale, or source-editor commentary as memories.
First-person storytelling describes whose experience is told, not a mandatory
first-person camera. Front-facing environmental portraits remain encouraged in
the human-figure path. Keep supported place, time, identity, action, and both
soundtrack contexts aligned; unspecified appearance is documented artistic
casting. The original podcast prompt path is otherwise unchanged.

For the optional `balanced` / **Balanced Memories** path, author a new sequence
of durable memory beats rather than alternately copying the contextual and
portrait prompts. Vary interactions, meaningful objects, actions, environmental
detail and human presence. Independent scene boundaries are allowed on the same
approved audio/caption clock. The active 136-story December revision uses a
five-second minimum; all other scopes and preserved legacy editions keep their existing minimum.
The five-second floor is not a required cutting rate. Use more distinct,
supported memory beats where they add content rather than dividing a single
image mechanically. Post-onset fades must fit the shorter scenes.
Keep short beats on the previous image. Distinguish remembered events from
future wishes and hypothetical places. Prefer physical crops or back views for
unknown faces; avoid reflection, double-exposure and diffusion wording that can
produce duplicated heads. Keep exclusion/attribution commentary in metadata or
negative prompts, not positive CLIP descriptions. Each path remains separately
reviewable; do not overwrite the retained two-path edition.

In story-detail revisions, spend the token budget on supported objects,
actions, relationships, spatial context and distinctive material details first.
Prefer a person doing the story's specific activity over a generic person
standing in an empty room. Replace abstract mood explanations with concrete
visible content where the evidence supports it; keep attribution and authenticity
disclaimers in metadata. Fit details into one coherent scene, not a collage.
Never invent props to meet a detail quota when a personal fragment is sparse.
Keep new events at or after their recorded speech anchor, and leave hopes,
unrealized plans and uncertain memories explicitly unresolved.

For the 2026-10-30 five-second revision, the user authorized one source-grounded
opening-context image at each story's exact start, so a previous person's image
does not carry into the new story. Restrict that opening to the supplied opening
context; disclose the story-introduction timing exception in metadata. Do not
use it to preview later events, places, relationships, or outcomes. Subsequent
details keep their measured material and semantic boundaries.
