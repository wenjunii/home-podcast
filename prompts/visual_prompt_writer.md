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
- When identity is unknown, avoid inventing a face. Prefer a back view, hands,
  silhouette, interior, landscape, meaningful object, letter, screen fragment,
  or other indirect representation.
- Do not turn grief, illness, war, children, or trauma into spectacle.
- Do not invent readable text, logos, flags, famous monuments, architecture, or
  ceremonial clothing.
- When `complementary_prompt_context` is present, do not repeat its
  `avoid_existing_prompt` subject, framing, focal object, or camera angle.
  Create a materially different composition supported by the current child
  transcript and evidence.

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
