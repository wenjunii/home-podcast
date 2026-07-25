# Accent-aware host casting

The show rotates both people and accents between episodes. It does not assign
an accent line by line, alter the frozen cast during regeneration, or ask a
voice to imitate a nationality.

## Production policy

- English is the primary host language; native and multilingual varieties of
  English are welcome.
- Accent labels must come from verified provider metadata and a listening
  review.
- Each host must remain intelligible to a broad international audience without
  erasing the voice's natural character.
- Accent must never be a punchline, a proxy for intelligence, or a shortcut
  for assigning the archive expert, emotional host, or curious host.
- The casting algorithm first preserves unique people and role compatibility,
  then maximizes distinct accents, then applies a deterministic episode hash.
- Saving `episodes/<episode>/cast.json` freezes the result.

## Candidate gate

`config/accent_voice_candidates.json` contains metadata-screened Voice Library
candidates. Inclusion there does not make a voice eligible for production.
Every candidate currently has:

- verified English metadata
- a 730-day availability notice
- a 1x credit rate
- at least one proposed conversational role

The same 628-character audition passage tests light humor, a tonal transition,
archive uncertainty, emotional restraint, and the pronunciation of Kenya and
Sehnsucht. Prepare it with:

```powershell
python -m home_podcast prepare-voice-audition `
  --audition .\episodes\2013-12.01\accent-voice-audition.json `
  --candidates .\config\accent_voice_candidates.json

python -m home_podcast generate-tts `
  --jobs .\work\tts\accent-voice-audition-2026-07-jobs.jsonl
```

The dry run is safe and makes no provider call. Paid generation additionally
requires `--execute`, `--max-credits`, and `ELEVENLABS_API_KEY` in the process
environment. Keys are never stored in jobs, metadata, or source control.

## July 2026 audition

Nine 192 kbps listening copies were generated locally:

| Candidate | Accent | Locale | Proposed fit |
| --- | --- | --- | --- |
| Jessica | Irish | en-IE | Curious guide, archive nerd |
| Isla | Scottish | en-GB | Curious guide, connector |
| Monika | Indian English | en-IN | Curious guide, connector |
| Thandi | South African English | en-ZA | Archive nerd, connector |
| Stella | Nigerian English | en-NG | Curious guide, connector |
| Danielle | Canadian | en-CA | Curious guide, connector |
| Chloe | French-influenced English | en-GB | Curious guide, connector |
| Ernesto | Spanish-influenced English | en-US | Archive nerd, connector |
| Lee | Chinese-influenced English | en-GB | Archive nerd, connector |

The retained generations used 3,105 credits. An interrupted provider request
used another 345 credits before its response could be cached, so the account
recorded 3,450 credits for this run. Durations range from 34.85 to 46.21
seconds. All files verify at approximately 192 kbps and peak below 0 dBFS.
Production will normalize the considerable audition-level loudness differences.

## Listening rubric

Score each sample from 1–5 for:

1. Natural, friend-like delivery
2. Emotional range without melodrama
3. Clarity for a general international audience
4. Warmth, curiosity, and timing
5. Pronunciation of names and multilingual fragments
6. Smooth movement from humor to seriousness
7. Long-form listening fatigue
8. Audio artifacts
9. Fit for each proposed role
10. Absence of caricature

A candidate enters `config/voice_roster.json` only after listening approval.
The pilot's Maya, Theo, and Lina cast remains frozen.

## Durability

Voice Library entries are external dependencies even with long notice periods.
Keep audition contracts and candidate metadata versioned so a withdrawn voice
can be replaced without changing published episodes. ElevenLabs says its
current default voices expire on December 31, 2026, so approved future hosts
should move toward stable community or explicitly authorized custom voices.
