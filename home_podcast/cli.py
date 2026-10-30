from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .analysis import (
    export_analysis_packets,
    export_story_cards,
    import_story_cards,
)
from .audio import (
    render_dialogue_episode_audio,
    render_episode_audio,
    render_soundscape_audio,
)
from .casting import create_episode_cast
from .catalog import catalog_status
from .config import ProjectConfig
from .doctor import run_doctor
from .dialogue_runner import (
    generate_dialogue_audition_jobs,
    generate_dialogue_episode_jobs,
    prepare_dialogue_audition_jobs,
    prepare_dialogue_episode_jobs,
)
from .editor import trim_episode_script
from .ingest import ingest_exports
from .planning import create_month_proposal, lock_episode_manifest, prepare_script_packet
from .planning import snapshot_crawl_month
from .polisher import polish_episode_conversation
from .provider_runner import analyze_story_jobs
from .script import prepare_tts_jobs, validate_script
from .script_runner import generate_episode_script
from .scene_soundscape import validate_scene_soundscape
from .sfx_runner import generate_sound_effect_jobs
from .sound_design import prepare_sfx_jobs, validate_sound_design
from .live_storytelling import (
    execute_live_variation,
    live_storytelling_doctor,
    prepare_live_variation,
    read_live_control,
    run_live_worker,
    update_live_control,
)
from .local_audio import (
    approve_local_voice,
    assemble_local_speech,
    assemble_local_speech_collection,
    assemble_local_soundscape_collection,
    generate_local_ambient,
    generate_local_speech,
    generate_local_voice_audition,
    local_audio_doctor,
    prepare_local_ambient,
    prepare_local_ambient_collection,
    prepare_local_speech_jobs,
    prepare_local_voice_audition,
)
from .storytelling import (
    create_storytelling_cast,
    create_storytelling_plan,
    export_storytelling_jobs,
    import_storytelling_adaptations,
    validate_storytelling_adaptation,
)
from .transcripts import render_transcripts
from .tts_runner import generate_tts_jobs
from .visual_prompt_runner import (
    generate_visual_prompt_jobs,
    import_visual_prompt_results,
)
from .visuals import (
    expand_visual_scenes,
    prepare_visual_scenes,
    validate_visual_plan,
)
from .voice_audition import prepare_voice_candidate_audition_jobs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="home-podcast",
        description=(
            "Incremental production pipeline for Recovered Homes storytelling "
            "and its preserved podcast format."
        ),
    )
    parser.add_argument(
        "--config",
        default="podcast.json",
        help="Path to a Recovered Homes project config JSON",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("doctor", help="Check local project and pilot prerequisites")
    subparsers.add_parser("ingest", help="Incrementally ingest stories_*.md exports")

    status = subparsers.add_parser("status", help="Show catalog coverage and crawl months")
    status.add_argument("--month", help="Restrict counts to YYYY-MM")

    export = subparsers.add_parser(
        "export-analysis", help="Export uncached stories as provider-neutral JSONL jobs"
    )
    export.add_argument("--month", help="Restrict to crawl month YYYY-MM")
    export.add_argument("--cohort", help="Frozen cohort manifest to restrict exact stories")
    export.add_argument("--output", help="Output JSONL path")
    export.add_argument("--limit", type=int)
    export.add_argument("--include-existing", action="store_true")

    export_cards = subparsers.add_parser(
        "export-cards", help="Export current story cards as portable JSONL"
    )
    export_cards.add_argument("--month", help="Restrict to crawl month YYYY-MM")
    export_cards.add_argument("--output", help="Output JSONL path")

    import_cards = subparsers.add_parser(
        "import-cards", help="Import model-produced story cards from JSONL"
    )
    import_cards.add_argument("input", help="Story-card JSONL path")
    import_cards.add_argument(
        "--analyzer",
        help="Override embedded analyzer metadata (requires --analyzer-version)",
    )
    import_cards.add_argument(
        "--analyzer-version",
        help="Override embedded analyzer metadata (requires --analyzer)",
    )

    snapshot = subparsers.add_parser(
        "snapshot-volume", help="Freeze the current stories in a crawl-month cohort"
    )
    snapshot.add_argument("--month", required=True)
    snapshot.add_argument("--label", default="pilot")
    snapshot.add_argument(
        "--analyzed-only",
        action="store_true",
        help="Freeze only stories that already have a current story card",
    )
    snapshot.add_argument(
        "--theme",
        help="Freeze only eligible analyzed stories with this primary theme",
    )
    snapshot.add_argument("--output", help="Cohort JSON path")

    analyze = subparsers.add_parser(
        "analyze", help="Analyze exported story jobs with the configured LLM"
    )
    analyze.add_argument("--input", required=True, help="Story jobs JSONL path")
    analyze.add_argument("--workers", type=int, default=3)
    analyze.add_argument("--limit", type=int)

    plan = subparsers.add_parser(
        "plan", help="Create a maximum-coverage thematic proposal for a crawl month"
    )
    plan.add_argument("--month", required=True)
    plan.add_argument("--cohort", help="Frozen cohort manifest to restrict exact stories")
    plan.add_argument(
        "--single-episode",
        action="store_true",
        help="Combine every eligible cohort story into one proposed episode",
    )
    plan.add_argument(
        "--information-driven",
        action="store_true",
        default=None,
        help=(
            "Keep every eligible story in its thematic installment and derive "
            "runtime from the information instead of a fixed story/time target"
        ),
    )
    plan.add_argument(
        "--title",
        help="Override the title when the proposal contains exactly one episode",
    )
    plan.add_argument("--output", help="Proposal JSON path")

    storytelling_plan = subparsers.add_parser(
        "plan-storytelling",
        help="Create one evidence-grounded narration assignment per eligible story",
    )
    storytelling_plan.add_argument("--month", required=True)
    storytelling_plan.add_argument("--output", help="Storytelling plan JSON path")

    storytelling_export = subparsers.add_parser(
        "export-storytelling",
        help="Export uncached self-narrated adaptation jobs without network calls",
    )
    storytelling_export.add_argument("--plan", required=True)
    storytelling_export.add_argument("--output", help="Adaptation jobs JSONL path")
    storytelling_export.add_argument("--include-existing", action="store_true")
    storytelling_export.add_argument("--limit", type=int)

    storytelling_import = subparsers.add_parser(
        "import-storytelling",
        help="Validate and import locally authored story adaptations",
    )
    storytelling_import.add_argument("--input", required=True)
    storytelling_import.add_argument("--jobs", required=True)
    storytelling_import.add_argument("--report", help="Import report JSON path")

    storytelling_validate = subparsers.add_parser(
        "validate-storytelling",
        help="Validate one adaptation against its exact source job",
    )
    storytelling_validate.add_argument("--adaptation", required=True)
    storytelling_validate.add_argument("--job", required=True)

    storytelling_cast = subparsers.add_parser(
        "cast-storytelling",
        help="Select and freeze one auditioned narrator for an adaptation",
    )
    storytelling_cast.add_argument("--narration", required=True)
    storytelling_cast.add_argument("--adaptation")
    storytelling_cast.add_argument("--output")

    live_doctor = subparsers.add_parser(
        "live-storytelling-doctor",
        help="Check one local storytelling runtime profile without loading models",
    )
    live_doctor.add_argument(
        "--profile",
        choices=("3080_safe", "5090_live"),
        default="3080_safe",
    )
    live_doctor.add_argument("--skip-ollama", action="store_true")

    live_control = subparsers.add_parser(
        "set-live-storytelling",
        help="Update the file-based Show Control state used by the local worker",
    )
    live_control.add_argument(
        "--profile", choices=("3080_safe", "5090_live")
    )
    live_enabled = live_control.add_mutually_exclusive_group()
    live_enabled.add_argument("--enable", action="store_true")
    live_enabled.add_argument("--disable", action="store_true")
    for name in ("narration", "speech", "visual"):
        group = live_control.add_mutually_exclusive_group()
        group.add_argument(f"--{name}-variation", action="store_true")
        group.add_argument(f"--canonical-{name}", action="store_true")
    live_control.add_argument(
        "--casting-mode",
        choices=("evidence_conservative", "interpretive"),
    )
    live_control.add_argument("--seed-mode", choices=("fixed", "random"))
    live_control.add_argument("--fixed-seed", type=int)
    live_control.add_argument("--narration")
    live_control.add_argument("--visuals")
    live_control.add_argument("--human-visuals")
    live_control.add_argument("--regenerate", action="store_true")

    live_prepare = subparsers.add_parser(
        "prepare-live-variation",
        help="Prepare a no-network, exact-call-ceiling local variation request",
    )
    live_prepare.add_argument("--narration", required=True)
    live_prepare.add_argument(
        "--profile",
        choices=("3080_safe", "5090_live"),
        default="5090_live",
    )
    live_prepare.add_argument("--loop-index", type=int, required=True)
    live_prepare.add_argument(
        "--casting-mode",
        choices=("evidence_conservative", "interpretive"),
        default="interpretive",
    )
    live_prepare.add_argument("--seed", type=int)
    live_prepare.add_argument("--visuals")
    live_prepare.add_argument("--human-visuals")

    live_execute = subparsers.add_parser(
        "execute-live-variation",
        help="Run a prepared variation through local Ollama and Qwen3-TTS",
    )
    live_execute.add_argument("--request", required=True)
    live_execute.add_argument("--canonical-narration", action="store_true")
    live_execute.add_argument("--canonical-speech", action="store_true")
    live_execute.add_argument("--canonical-visuals", action="store_true")

    live_worker = subparsers.add_parser(
        "run-live-storytelling-worker",
        help="Watch Show Control state and build validated next-loop buffers locally",
    )
    live_worker.add_argument("--once", action="store_true")
    live_worker.add_argument("--poll-seconds", type=float, default=0.5)
    live_worker.add_argument("--max-iterations", type=int)

    story_audio = subparsers.add_parser(
        "story-audio", help="Resumable whole-story VoiceDesign production on the offline 3080"
    )
    story_audio.add_argument("stage", choices=("queue", "prepare", "render", "audit", "quality", "package", "verify", "approve"))
    story_audio.add_argument("--brief")
    story_audio.add_argument("--production-index")
    story_audio.add_argument("--limit", type=int, default=25)
    story_audio.add_argument("--profile", default="3080_offline_production")
    story_audio.add_argument("--execute", action="store_true")
    story_audio.add_argument("--max-calls", type=int)
    story_audio.add_argument("--reviewer")
    story_audio.add_argument("--approval-note")

    ambient_batch = subparsers.add_parser(
        "ambient-batch", help="Evidence-bound offline CUDA soundscapes for approved narrations"
    )
    ambient_batch.add_argument("stage", choices=("prepare", "dry-run", "render", "quality", "audit", "package", "verify"))
    ambient_batch.add_argument("--brief", required=True)
    ambient_batch.add_argument("--execute", action="store_true")
    ambient_batch.add_argument("--max-calls", type=int)

    local_doctor = subparsers.add_parser(
        "local-audio-doctor",
        help="Check the sequential 3080 offline-audio runtime without loading models",
    )
    local_doctor.add_argument("--profile", default="3080_offline_production")
    local_doctor.add_argument("--local-audio-config")
    local_doctor.add_argument(
        "--component", choices=("all", "qwen", "ambient"), default="all"
    )

    local_audition_prepare = subparsers.add_parser(
        "prepare-local-voice-audition",
        help="Build a diverse, no-network Qwen VoiceDesign audition plan",
    )
    local_audition_prepare.add_argument("--production-index")
    local_audition_prepare.add_argument("--output")
    local_audition_prepare.add_argument("--profile", default="3080_offline_production")
    local_audition_prepare.add_argument("--local-audio-config")
    local_audition_prepare.add_argument("--voice-limit", type=int)

    local_audition_generate = subparsers.add_parser(
        "generate-local-voice-audition",
        help="Dry-run or resumably execute the local Qwen VoiceDesign audition",
    )
    local_audition_generate.add_argument("--plan", required=True)
    local_audition_generate.add_argument("--execute", action="store_true")
    local_audition_generate.add_argument("--max-calls", type=int)
    local_audition_generate.add_argument("--limit", type=int)
    local_audition_generate.add_argument("--allow-model-download", action="store_true")
    local_audition_generate.add_argument("--local-audio-config")

    local_voice_approve = subparsers.add_parser(
        "approve-local-voice",
        help="Record one reviewed synthetic audition voice in the local roster",
    )
    local_voice_approve.add_argument("--plan", required=True)
    local_voice_approve.add_argument("--voice-id", required=True)
    local_voice_approve.add_argument("--reviewer", required=True)
    local_voice_approve.add_argument("--roster")

    local_speech_prepare = subparsers.add_parser(
        "prepare-local-speech",
        help="Freeze approved local casts and export resumable section TTS jobs",
    )
    local_speech_prepare.add_argument("--production-index")
    local_speech_prepare.add_argument("--roster")
    local_speech_prepare.add_argument("--output")
    local_speech_prepare.add_argument("--profile", default="3080_offline_production")
    local_speech_prepare.add_argument("--local-audio-config")
    local_speech_prepare.add_argument("--narration-limit", type=int)
    local_speech_prepare.add_argument(
        "--allow-conservative-editions",
        action="store_true",
        help="Include editions carrying the explicit conservative-spoken-edition warning",
    )

    local_speech_generate = subparsers.add_parser(
        "generate-local-speech",
        help="Dry-run or resumably execute cached Qwen voice-clone section jobs",
    )
    local_speech_generate.add_argument("--jobs", required=True)
    local_speech_generate.add_argument("--execute", action="store_true")
    local_speech_generate.add_argument("--max-calls", type=int)
    local_speech_generate.add_argument("--limit", type=int)
    local_speech_generate.add_argument("--allow-model-download", action="store_true")
    local_speech_generate.add_argument("--profile", default="3080_offline_production")
    local_speech_generate.add_argument("--local-audio-config")

    local_speech_assemble = subparsers.add_parser(
        "assemble-local-speech",
        help="Assemble cached narration sections into voices-only audio and captions",
    )
    local_speech_assemble.add_argument("--jobs", required=True)
    local_speech_assemble.add_argument("--narration", required=True)
    local_speech_assemble.add_argument("--output-dir")

    local_speech_assemble_all = subparsers.add_parser(
        "assemble-local-speech-collection",
        help="Assemble every complete narration while reporting incomplete ones",
    )
    local_speech_assemble_all.add_argument("--jobs", required=True)
    local_speech_assemble_all.add_argument("--narration-limit", type=int)

    speech_master = subparsers.add_parser(
        "master-local-speech",
        help="Make a level-consistent playback copy of an existing WAV; no TTS calls",
    )
    speech_master.add_argument("--audio", required=True)
    speech_master.add_argument("--output-dir", required=True)
    speech_master.add_argument("--asr-report")

    local_ambient_prepare = subparsers.add_parser(
        "prepare-local-ambient",
        help="Create continuous evidence-conservative Stable Audio jobs for one narration",
    )
    local_ambient_prepare.add_argument("--timeline", required=True)
    local_ambient_prepare.add_argument("--adaptation", required=True)
    local_ambient_prepare.add_argument("--sound-design", required=True)
    local_ambient_prepare.add_argument("--jobs", required=True)
    local_ambient_prepare.add_argument("--profile", default="3080_offline_production")
    local_ambient_prepare.add_argument("--local-audio-config")

    local_ambient_generate = subparsers.add_parser(
        "generate-local-ambient",
        help="Dry-run or resumably execute Stable Audio 3 ambient jobs",
    )
    local_ambient_generate.add_argument("--jobs", required=True)
    local_ambient_generate.add_argument("--execute", action="store_true")
    local_ambient_generate.add_argument("--max-calls", type=int)
    local_ambient_generate.add_argument("--limit", type=int)
    local_ambient_generate.add_argument("--allow-model-download", action="store_true")
    local_ambient_generate.add_argument("--profile", default="3080_offline_production")
    local_ambient_generate.add_argument("--local-audio-config")

    local_ambient_prepare_all = subparsers.add_parser(
        "prepare-local-ambient-collection",
        help="Prepare continuous Stable Audio plans for all assembled narrations",
    )
    local_ambient_prepare_all.add_argument("--production-index")
    local_ambient_prepare_all.add_argument("--output")
    local_ambient_prepare_all.add_argument(
        "--profile", default="3080_offline_production"
    )
    local_ambient_prepare_all.add_argument("--local-audio-config")
    local_ambient_prepare_all.add_argument("--narration-limit", type=int)

    local_soundscape_assemble_all = subparsers.add_parser(
        "assemble-local-soundscape-collection",
        help="Render all complete voices-only and soundscape-only story tracks",
    )
    local_soundscape_assemble_all.add_argument("--production-index")
    local_soundscape_assemble_all.add_argument("--narration-limit", type=int)

    lock = subparsers.add_parser(
        "lock-episode", help="Freeze one proposed installment as an episode manifest"
    )
    lock.add_argument("--proposal", required=True)
    lock.add_argument("--episode", required=True)

    cast = subparsers.add_parser(
        "cast-episode",
        help="Select and freeze a rotating three-person voice cast for an episode",
    )
    cast.add_argument("--episode", required=True)
    cast.add_argument("--output", help="Episode cast JSON path")

    packet = subparsers.add_parser(
        "prepare-script", help="Build a source-grounded script evidence packet"
    )
    source_group = packet.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--manifest", help="Preferred locked episode manifest")
    source_group.add_argument("--proposal", help="Uncommitted proposal for preview use")
    packet.add_argument("--episode", required=True)
    packet.add_argument("--output", help="Evidence packet JSON path")

    validate = subparsers.add_parser(
        "validate-script", help="Validate grounding and story coverage in a script"
    )
    validate.add_argument("--script", required=True)
    validate.add_argument("--evidence", required=True)

    generate_script = subparsers.add_parser(
        "generate-script",
        help="Generate and source-validate a complete episode script",
    )
    generate_script.add_argument("--evidence", required=True)
    generate_script.add_argument(
        "--outline",
        help="Episode movement outline; defaults to episodes/<episode>/outline.json",
    )
    generate_script.add_argument(
        "--output",
        help="Validated script JSON path; defaults to the episode directory",
    )

    trim_script = subparsers.add_parser(
        "trim-script",
        help="Create and apply a deletion-only editorial trim plan",
    )
    trim_script.add_argument("--script", required=True)
    trim_script.add_argument("--evidence", required=True)
    trim_script.add_argument("--target-min", type=int, default=4400)
    trim_script.add_argument("--target-max", type=int, default=4600)
    trim_script.add_argument(
        "--plan",
        help="Apply a saved deletion plan without making a provider call",
    )
    trim_script.add_argument(
        "--output",
        help="Validated trimmed script path; defaults to replacing --script",
    )

    polish_script = subparsers.add_parser(
        "polish-script",
        help="Polish a grounded script into natural, friend-like host conversation",
    )
    polish_script.add_argument("--script", required=True)
    polish_script.add_argument("--evidence", required=True)
    polish_script.add_argument("--cast", required=True)
    polish_script.add_argument("--target-min", type=int, default=4400)
    polish_script.add_argument("--target-max", type=int, default=4600)
    polish_script.add_argument(
        "--max-new-calls",
        type=int,
        help="Generate at most this many uncached sections, then stop resumably",
    )
    polish_script.add_argument(
        "--output",
        help="Validated polished script path; defaults to replacing --script",
    )

    tts = subparsers.add_parser(
        "prepare-tts", help="Create cached, segment-level TTS jobs from a valid script"
    )
    tts.add_argument("--script", required=True)
    tts.add_argument("--output", help="TTS jobs JSONL path")
    tts.add_argument("--provider", required=True)
    tts.add_argument("--model", required=True)
    tts.add_argument(
        "--cast",
        help="Frozen episode cast; defaults to episodes/<episode>/cast.json",
    )

    generate_tts = subparsers.add_parser(
        "generate-tts",
        help="Dry-run or execute cached ElevenLabs speech jobs",
    )
    generate_tts.add_argument("--jobs", required=True)
    generate_tts.add_argument("--limit", type=int)
    generate_tts.add_argument(
        "--execute",
        action="store_true",
        help="Make paid provider calls; otherwise report pending cost only",
    )
    generate_tts.add_argument(
        "--max-credits",
        type=float,
        help="Required spending ceiling when --execute is used",
    )

    prepare_voice_audition = subparsers.add_parser(
        "prepare-voice-audition",
        help="Create same-script TTS jobs for screened accent candidates",
    )
    prepare_voice_audition.add_argument("--audition", required=True)
    prepare_voice_audition.add_argument("--candidates", required=True)
    prepare_voice_audition.add_argument("--output", help="Voice audition jobs JSONL path")

    prepare_dialogue = subparsers.add_parser(
        "prepare-dialogue-audition",
        help="Create cached multi-speaker ElevenLabs dialogue audition jobs",
    )
    prepare_dialogue.add_argument("--audition", required=True)
    prepare_dialogue.add_argument("--cast", required=True)
    prepare_dialogue.add_argument("--output", help="Dialogue jobs JSONL path")

    generate_dialogue = subparsers.add_parser(
        "generate-dialogue-audition",
        help="Dry-run or execute cached ElevenLabs dialogue audition jobs",
    )
    generate_dialogue.add_argument("--jobs", required=True)
    generate_dialogue.add_argument(
        "--variant",
        help="Generate only one named audition variant",
    )
    generate_dialogue.add_argument(
        "--execute",
        action="store_true",
        help="Make paid provider calls; otherwise report pending cost only",
    )
    generate_dialogue.add_argument(
        "--max-credits",
        type=float,
        help="Required spending ceiling when --execute is used",
    )

    prepare_dialogue_episode = subparsers.add_parser(
        "prepare-dialogue-episode",
        help="Chunk a complete episode for contextual timestamped dialogue generation",
    )
    prepare_dialogue_episode.add_argument("--script", required=True)
    prepare_dialogue_episode.add_argument("--cast", required=True)
    prepare_dialogue_episode.add_argument(
        "--performance",
        required=True,
        help="Dialogue audition or performance contract containing the selected settings",
    )
    prepare_dialogue_episode.add_argument(
        "--variant",
        default="creative-plus",
        help="Settings variant from --performance",
    )
    prepare_dialogue_episode.add_argument(
        "--output",
        help="Episode dialogue jobs JSONL path",
    )

    generate_dialogue_episode = subparsers.add_parser(
        "generate-dialogue-episode",
        help="Dry-run or execute resumable timestamped episode dialogue jobs",
    )
    generate_dialogue_episode.add_argument("--jobs", required=True)
    generate_dialogue_episode.add_argument("--limit", type=int)
    generate_dialogue_episode.add_argument(
        "--execute",
        action="store_true",
        help="Make paid provider calls; otherwise report pending cost only",
    )
    generate_dialogue_episode.add_argument(
        "--max-credits",
        type=float,
        help="Required spending ceiling when --execute is used",
    )

    validate_sound = subparsers.add_parser(
        "validate-sound-design",
        help="Validate a sound-design cue sheet against its episode script",
    )
    validate_sound.add_argument("--sound-design", required=True)
    validate_sound.add_argument("--script", required=True)

    validate_scene_sound = subparsers.add_parser(
        "validate-scene-soundscape",
        help="Validate one continuous non-speech cue per visual scene",
    )
    validate_scene_sound.add_argument("--sound-design", required=True)
    validate_scene_sound.add_argument("--visuals", required=True)
    validate_scene_sound.add_argument("--timeline", required=True)

    sfx = subparsers.add_parser(
        "prepare-sfx",
        help="Create cached, provider-neutral jobs for generated sound cues",
    )
    sfx.add_argument("--sound-design", required=True)
    sfx.add_argument("--script", required=True)
    sfx.add_argument("--output", help="SFX jobs JSONL path")
    sfx.add_argument("--provider", required=True)
    sfx.add_argument("--model", required=True)

    generate_sfx = subparsers.add_parser(
        "generate-sfx",
        help="Dry-run or execute cached ElevenLabs sound-effect jobs",
    )
    generate_sfx.add_argument("--jobs", required=True)
    generate_sfx.add_argument("--limit", type=int)
    generate_sfx.add_argument(
        "--execute",
        action="store_true",
        help="Make paid provider calls; otherwise report pending cost only",
    )
    generate_sfx.add_argument(
        "--max-credits",
        type=float,
        help="Required spending ceiling when --execute is used",
    )

    audio = subparsers.add_parser(
        "render-audio",
        help="Normalize and mix completed speech clips with optional sound design",
    )
    audio.add_argument("--jobs", required=True)
    audio.add_argument("--output-dir", help="Episode audio output directory")
    audio.add_argument("--sound-design", help="Optional sound-design cue sheet")
    audio.add_argument(
        "--sfx-jobs",
        help="Completed generated-SFX jobs referenced by the sound-design cue sheet",
    )

    dialogue_audio = subparsers.add_parser(
        "render-dialogue-audio",
        help="Render timestamped contextual dialogue with optional sound design",
    )
    dialogue_audio.add_argument("--jobs", required=True)
    dialogue_audio.add_argument(
        "--output-dir",
        help="Episode audio output directory",
    )
    dialogue_audio.add_argument(
        "--sound-design",
        help="Optional sound-design cue sheet",
    )
    dialogue_audio.add_argument(
        "--sfx-jobs",
        help="Completed generated-SFX jobs referenced by the sound-design cue sheet",
    )

    soundscape_audio = subparsers.add_parser(
        "render-soundscape",
        help="Render sound design against an existing reviewed audio timeline",
    )
    soundscape_audio.add_argument("--timeline", required=True)
    soundscape_audio.add_argument("--sound-design", required=True)
    soundscape_audio.add_argument(
        "--sfx-jobs",
        help="Completed generated-SFX jobs referenced by the sound-design cue sheet",
    )
    soundscape_audio.add_argument(
        "--voices-audio",
        help="Optional reviewed voices-only track for a combined preview",
    )
    soundscape_audio.add_argument(
        "--output-dir",
        help="Episode audio output directory",
    )

    transcript = subparsers.add_parser(
        "transcript", help="Render Markdown, WebVTT, and SRT from an audio timeline"
    )
    transcript.add_argument("--timeline", required=True)
    transcript.add_argument("--output-dir", help="Transcript output directory")
    transcript.add_argument(
        "--cast",
        help="Frozen episode cast; defaults to episodes/<episode>/cast.json",
    )
    transcript.add_argument(
        "--speech-only",
        action="store_true",
        help="Exclude soundscape cues and write *-voices-only transcript files",
    )

    visuals = subparsers.add_parser(
        "prepare-visuals",
        help="Create long, story-centered visual scenes from a speech timeline",
    )
    visuals.add_argument("--timeline", required=True)
    visuals.add_argument("--output", help="Versioned visual scene JSON")
    visuals.add_argument(
        "--jobs",
        help="Grounded visual-prompt JSONL jobs; defaults under work/visuals",
    )
    visuals.add_argument(
        "--min-scene-seconds",
        type=float,
        default=15.0,
        help="Merge shorter passages instead of generating a disposable image",
    )
    visuals.add_argument(
        "--crossfade-seconds",
        type=float,
        default=5.0,
    )

    expand_visuals = subparsers.add_parser(
        "expand-visuals",
        help="Split long generated scenes and create only complementary prompt jobs",
    )
    expand_visuals.add_argument("--source-visuals", required=True)
    expand_visuals.add_argument("--timeline", required=True)
    expand_visuals.add_argument("--output", required=True)
    expand_visuals.add_argument("--jobs", required=True)
    expand_visuals.add_argument(
        "--min-scene-seconds",
        type=float,
        default=15.0,
    )
    expand_visuals.add_argument(
        "--max-scene-seconds",
        type=float,
        default=35.0,
    )
    expand_visuals.add_argument(
        "--crossfade-seconds",
        type=float,
        default=5.0,
    )

    validate_visuals = subparsers.add_parser(
        "validate-visuals",
        help="Validate scene coverage, prompt chunks, and grounding review state",
    )
    validate_visuals.add_argument("--visuals", required=True)

    generate_visuals = subparsers.add_parser(
        "generate-visual-prompts",
        help="Dry-run or execute resumable grounded SDXL prompt generation",
    )
    generate_visuals.add_argument("--jobs", required=True)
    generate_visuals.add_argument("--visuals", required=True)
    generate_visuals.add_argument(
        "--output",
        help="Updated visual scene plan; defaults to replacing --visuals atomically",
    )
    generate_visuals.add_argument(
        "--model",
        help="Optional visual-provider model override",
    )
    generate_visuals.add_argument(
        "--tokenizer-model",
        help=(
            "Local SDXL model/snapshot path or cached Hugging Face model ID; "
            "defaults to the visual plan model"
        ),
    )
    generate_visuals.add_argument("--limit", type=int)
    generate_visuals.add_argument(
        "--execute",
        action="store_true",
        help="Make paid provider calls; otherwise report cache and pending work",
    )
    generate_visuals.add_argument(
        "--max-calls",
        type=int,
        help="Required hard ceiling on new paid calls when --execute is used",
    )
    generate_visuals.add_argument(
        "--retry-invalid",
        action="store_true",
        help="Replace previously cached but invalid raw model responses",
    )

    import_visuals = subparsers.add_parser(
        "import-visual-prompts",
        help="Validate and apply locally authored visual prompts without network calls",
    )
    import_visuals.add_argument("--input", required=True)
    import_visuals.add_argument("--jobs", required=True)
    import_visuals.add_argument("--visuals", required=True)
    import_visuals.add_argument("--output")
    import_visuals.add_argument(
        "--model-label",
        default="codex-interactive",
    )
    import_visuals.add_argument("--tokenizer-model")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = ProjectConfig.load(args.config)
        config.ensure_runtime_directories()
        result = _dispatch(config, args)
        _print_json(result)
        if args.command == "validate-script" and not result["valid"]:
            return 2
        if args.command == "validate-storytelling" and not result["valid"]:
            return 2
        if args.command == "generate-script" and not result["valid"]:
            return 2
        if args.command == "trim-script" and not result["valid"]:
            return 2
        if (
            args.command == "polish-script"
            and result.get("complete")
            and not result["valid"]
        ):
            return 2
        if args.command == "validate-sound-design" and not result["valid"]:
            return 2
        if args.command == "validate-scene-soundscape" and not result["valid"]:
            return 2
        if args.command == "validate-visuals" and not result["valid"]:
            return 2
        if (
            args.command
            in {
                "generate-dialogue-audition",
                "generate-dialogue-episode",
                "generate-sfx",
                "generate-tts",
                "generate-visual-prompts",
                "generate-local-voice-audition",
                "generate-local-speech",
                "generate-local-ambient",
            }
            and result["execution_requested"]
            and result["failed"]
        ):
            return 2
        return 0
    except (FileNotFoundError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


def _dispatch(config: ProjectConfig, args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "doctor":
        return run_doctor(config)
    if args.command == "ingest":
        return vars(ingest_exports(config.catalog_path, config.exports_dir))
    if args.command == "status":
        if not config.catalog_path.exists():
            raise FileNotFoundError("Catalog does not exist; run ingest first")
        return catalog_status(config.catalog_path, args.month)
    if args.command == "export-analysis":
        suffix = args.month or "all"
        output = _path_or_default(
            args.output, config.work_dir / "analysis" / f"{suffix}-story-jobs.jsonl"
        )
        count = export_analysis_packets(
            config,
            output,
            month=args.month,
            cohort_path=Path(args.cohort).resolve() if args.cohort else None,
            include_existing=args.include_existing,
            limit=args.limit,
        )
        return {"exported": count, "output": str(output)}
    if args.command == "export-cards":
        suffix = args.month or "current"
        output = _path_or_default(
            args.output,
            config.project_root / "data" / "story_cards" / f"{suffix}-cards.jsonl",
        )
        count = export_story_cards(config, output, month=args.month)
        return {"exported": count, "output": str(output)}
    if args.command == "import-cards":
        imported, skipped = import_story_cards(
            config,
            Path(args.input).resolve(),
            analyzer=args.analyzer,
            analyzer_version=args.analyzer_version,
        )
        return {"imported": imported, "skipped_stale_or_missing": skipped}
    if args.command == "snapshot-volume":
        output = _path_or_default(
            args.output,
            config.project_root / "cohorts" / f"{args.month}-{args.label}.json",
        )
        snapshot, created = snapshot_crawl_month(
            config,
            args.month,
            args.label,
            output,
            analyzed_only=args.analyzed_only,
            primary_theme=args.theme,
        )
        return {
            "output": str(output),
            "created": created,
            "story_count": snapshot["story_count"],
            "crawl_month": snapshot["crawl_month"],
        }
    if args.command == "analyze":
        return analyze_story_jobs(
            config,
            Path(args.input).resolve(),
            workers=max(1, args.workers),
            limit=args.limit,
        )
    if args.command == "plan":
        output = _path_or_default(
            args.output, config.work_dir / "planning" / f"{args.month}-proposal.json"
        )
        proposal = create_month_proposal(
            config,
            args.month,
            output,
            cohort_path=Path(args.cohort).resolve() if args.cohort else None,
            single_episode=args.single_episode,
            single_episode_title=args.title,
            information_driven=args.information_driven,
        )
        return {
            "output": str(output),
            "installments": len(proposal["installments"]),
            **proposal["coverage"],
        }
    if args.command == "plan-storytelling":
        output = _path_or_default(
            args.output,
            config.work_dir / "planning" / f"{args.month}-storytelling-plan.json",
        )
        storytelling_plan = create_storytelling_plan(
            config,
            args.month,
            output,
        )
        return {
            "output": str(output),
            **storytelling_plan["coverage"],
            "network_calls": 0,
        }
    if args.command == "export-storytelling":
        plan_path = Path(args.plan).resolve()
        plan_value = json.loads(plan_path.read_text(encoding="utf-8"))
        month = str(plan_value.get("archive_volume", "storytelling"))
        output = _path_or_default(
            args.output,
            config.work_dir / "adaptations" / f"{month}-jobs.jsonl",
        )
        return export_storytelling_jobs(
            config,
            plan_path,
            output,
            include_existing=args.include_existing,
            limit=args.limit,
        )
    if args.command == "import-storytelling":
        report = _path_or_default(
            args.report,
            config.work_dir / "adaptations" / "import-report.json",
        )
        return import_storytelling_adaptations(
            config,
            Path(args.input).resolve(),
            Path(args.jobs).resolve(),
            report,
        )
    if args.command == "validate-storytelling":
        return validate_storytelling_adaptation(
            Path(args.adaptation).resolve(),
            Path(args.job).resolve(),
        )
    if args.command == "cast-storytelling":
        adaptation = _path_or_default(
            args.adaptation,
            config.episodes_dir / args.narration / "adaptation.json",
        )
        output = _path_or_default(
            args.output,
            config.episodes_dir / args.narration / "cast.json",
        )
        cast_value, created, pending_reason = create_storytelling_cast(
            config,
            args.narration,
            adaptation,
            output,
        )
        return {
            "output": str(output),
            "created": created,
            "narration_id": args.narration,
            "ready": cast_value is not None,
            "pending_reason": pending_reason,
            "narrator": cast_value.get("narrator") if cast_value else None,
            "network_calls": 0,
        }
    if args.command == "live-storytelling-doctor":
        return live_storytelling_doctor(
            config,
            profile_name=args.profile,
            check_ollama=not args.skip_ollama,
        )
    if args.command == "set-live-storytelling":
        changes: dict[str, Any] = {}
        if args.profile:
            changes["profile"] = args.profile
        if args.enable:
            changes["enabled"] = True
        elif args.disable:
            changes["enabled"] = False
        for name in ("narration", "speech", "visual"):
            if getattr(args, f"{name}_variation"):
                changes[f"{name}_variation"] = True
            elif getattr(args, f"canonical_{name}"):
                changes[f"{name}_variation"] = False
        if args.casting_mode:
            changes["casting_mode"] = args.casting_mode
        if args.seed_mode:
            changes["seed_mode"] = args.seed_mode
        if args.fixed_seed is not None:
            changes["fixed_seed"] = args.fixed_seed
        if args.narration is not None:
            changes["current_narration_id"] = args.narration
        if args.visuals is not None:
            changes["canonical_visuals"] = str(Path(args.visuals).resolve())
        if args.human_visuals is not None:
            changes["canonical_human_visuals"] = str(
                Path(args.human_visuals).resolve()
            )
        if args.regenerate:
            changes["regeneration_nonce"] = (
                int(read_live_control(config)["regeneration_nonce"]) + 1
            )
        control = update_live_control(config, changes)
        return {
            "control": control,
            "control_path": str(config.work_dir / "runtime" / "control.json"),
            "network_calls": 0,
            "paid_calls": 0,
        }
    if args.command == "prepare-live-variation":
        return prepare_live_variation(
            config,
            args.narration,
            profile_name=args.profile,
            loop_index=args.loop_index,
            casting_mode=args.casting_mode,
            seed=args.seed,
            canonical_visuals_path=(
                Path(args.visuals).resolve() if args.visuals else None
            ),
            canonical_human_visuals_path=(
                Path(args.human_visuals).resolve() if args.human_visuals else None
            ),
        )
    if args.command == "execute-live-variation":
        return execute_live_variation(
            config,
            Path(args.request).resolve(),
            narration_variation=not args.canonical_narration,
            speech_variation=not args.canonical_speech,
            visual_variation=not args.canonical_visuals,
        )
    if args.command == "run-live-storytelling-worker":
        return run_live_worker(
            config,
            once=args.once,
            poll_seconds=args.poll_seconds,
            max_iterations=args.max_iterations,
        )
    if args.command == "ambient-batch":
        from .ambient_batch import AmbientBatch
        runner = AmbientBatch(config, Path(args.brief))
        if args.stage == "render":
            return runner.render(execute=args.execute, max_calls=args.max_calls)
        result = getattr(runner, args.stage.replace("-", "_"))()
        if args.stage == "quality" and result.get("held_assets"):
            raise ValueError("Ambient assets held; see the saved quality report")
        if args.stage == "audit" and result.get("recognized_segments"):
            raise ValueError("Possible ambient speech; see the saved diagnostic")
        return result
    if args.command == "story-audio":
        from .local_audio import load_local_audio_config
        from .single_take_audio import MODEL, REVISION, SingleTakeProduction, read
        _, profile, _ = load_local_audio_config(config, profile_name=args.profile)
        narration = profile["narration"]
        if (narration.get("production_mode") != "single_take_voice_design"
                or narration.get("production_model") != MODEL
                or narration.get("production_model_revision") != REVISION):
            raise ValueError("story-audio requires the pinned single_take_voice_design offline profile")
        runner = SingleTakeProduction(config, model_path=(
            Path(narration["production_model_path"]) if narration.get("production_model_path") else None))
        if args.stage == "queue":
            if not args.production_index:
                raise ValueError("queue requires --production-index pointing to a reviewed production index")
            return runner.queue(Path(args.production_index).resolve(), limit=args.limit)
        if not args.brief:
            raise ValueError("This story-audio stage requires --brief with reviewed casting and delivery")
        brief = read(Path(args.brief).resolve())
        if args.stage == "prepare":
            return runner.prepare(brief)
        plan = read(runner.paths(brief)[0] / "plan.json")
        if args.stage == "render":
            return runner.render(brief, plan, execute=args.execute, max_calls=args.max_calls)
        if args.stage == "approve":
            return runner.approve(brief, plan, reviewer=args.reviewer or "", note=args.approval_note or "")
        return getattr(runner, args.stage)(brief, plan)
    if args.command == "local-audio-doctor":
        return local_audio_doctor(
            config,
            profile_name=args.profile,
            local_config_path=(
                Path(args.local_audio_config).resolve()
                if args.local_audio_config
                else None
            ),
            component=args.component,
        )
    if args.command == "prepare-local-voice-audition":
        return prepare_local_voice_audition(
            config,
            _path_or_default(
                args.production_index,
                config.project_root
                / "series"
                / "2013-12"
                / "storytelling-production-index.json",
            ),
            _path_or_default(
                args.output,
                config.work_dir / "local-audio" / "voice-audition-plan.json",
            ),
            profile_name=args.profile,
            local_config_path=(
                Path(args.local_audio_config).resolve()
                if args.local_audio_config
                else None
            ),
            voice_limit=args.voice_limit,
        )
    if args.command == "generate-local-voice-audition":
        return generate_local_voice_audition(
            config,
            Path(args.plan).resolve(),
            execute=args.execute,
            max_calls=args.max_calls,
            limit=args.limit,
            allow_model_download=args.allow_model_download,
            local_config_path=(
                Path(args.local_audio_config).resolve()
                if args.local_audio_config
                else None
            ),
        )
    if args.command == "approve-local-voice":
        return approve_local_voice(
            config,
            Path(args.plan).resolve(),
            args.voice_id,
            _path_or_default(
                args.roster, config.project_root / "config" / "local_voice_roster.json"
            ),
            reviewer=args.reviewer,
        )
    if args.command == "prepare-local-speech":
        return prepare_local_speech_jobs(
            config,
            _path_or_default(
                args.production_index,
                config.project_root
                / "series"
                / "2013-12"
                / "storytelling-production-index.json",
            ),
            _path_or_default(
                args.roster, config.project_root / "config" / "local_voice_roster.json"
            ),
            _path_or_default(
                args.output,
                config.work_dir / "local-audio" / "production-speech-jobs.jsonl",
            ),
            profile_name=args.profile,
            local_config_path=(
                Path(args.local_audio_config).resolve()
                if args.local_audio_config
                else None
            ),
            narration_limit=args.narration_limit,
            allow_conservative_editions=args.allow_conservative_editions,
        )
    if args.command == "generate-local-speech":
        return generate_local_speech(
            config,
            Path(args.jobs).resolve(),
            execute=args.execute,
            max_calls=args.max_calls,
            limit=args.limit,
            allow_model_download=args.allow_model_download,
            profile_name=args.profile,
            local_config_path=(
                Path(args.local_audio_config).resolve()
                if args.local_audio_config
                else None
            ),
        )
    if args.command == "assemble-local-speech":
        return assemble_local_speech(
            config,
            Path(args.jobs).resolve(),
            args.narration,
            output_dir=(Path(args.output_dir).resolve() if args.output_dir else None),
        )
    if args.command == "assemble-local-speech-collection":
        return assemble_local_speech_collection(
            config,
            Path(args.jobs).resolve(),
            narration_limit=args.narration_limit,
        )
    if args.command == "master-local-speech":
        from .speech_mastering import load_settings, master_speech

        result = master_speech(
            Path(args.audio), Path(args.output_dir), load_settings(config.project_root),
            asr_path=Path(args.asr_report) if args.asr_report else None,
        )
        return {key: value for key, value in result.items() if key not in {"metrics", "identity"}}
    if args.command == "prepare-local-ambient":
        return prepare_local_ambient(
            config,
            Path(args.timeline).resolve(),
            Path(args.adaptation).resolve(),
            Path(args.sound_design).resolve(),
            Path(args.jobs).resolve(),
            profile_name=args.profile,
            local_config_path=(
                Path(args.local_audio_config).resolve()
                if args.local_audio_config
                else None
            ),
        )
    if args.command == "generate-local-ambient":
        return generate_local_ambient(
            config,
            Path(args.jobs).resolve(),
            execute=args.execute,
            max_calls=args.max_calls,
            limit=args.limit,
            allow_model_download=args.allow_model_download,
            profile_name=args.profile,
            local_config_path=(
                Path(args.local_audio_config).resolve()
                if args.local_audio_config
                else None
            ),
        )
    if args.command == "prepare-local-ambient-collection":
        return prepare_local_ambient_collection(
            config,
            _path_or_default(
                args.production_index,
                config.project_root
                / "series"
                / "2013-12"
                / "storytelling-production-index.json",
            ),
            _path_or_default(
                args.output,
                config.work_dir / "local-audio" / "ambient-jobs.jsonl",
            ),
            profile_name=args.profile,
            local_config_path=(
                Path(args.local_audio_config).resolve()
                if args.local_audio_config
                else None
            ),
            narration_limit=args.narration_limit,
        )
    if args.command == "assemble-local-soundscape-collection":
        return assemble_local_soundscape_collection(
            config,
            _path_or_default(
                args.production_index,
                config.project_root
                / "series"
                / "2013-12"
                / "storytelling-production-index.json",
            ),
            narration_limit=args.narration_limit,
        )
    if args.command == "lock-episode":
        path, created = lock_episode_manifest(
            config, Path(args.proposal).resolve(), args.episode
        )
        return {"manifest": str(path), "created": created, "episode_id": args.episode}
    if args.command == "cast-episode":
        output = _path_or_default(
            args.output,
            config.episodes_dir / args.episode / "cast.json",
        )
        episode_cast, created = create_episode_cast(
            config.voice_roster_path,
            args.episode,
            output,
        )
        return {
            "output": str(output),
            "created": created,
            "episode_id": args.episode,
            "hosts": [
                {
                    "role": host["id"],
                    "display_name": host["display_name"],
                    "voice_name": host["voice_name"],
                    "accent": host["accent"],
                }
                for host in episode_cast["hosts"]
            ],
        }
    if args.command == "prepare-script":
        output = _path_or_default(
            args.output,
            config.work_dir / "scripts" / f"{args.episode}-evidence.json",
        )
        packet = prepare_script_packet(
            config,
            Path(args.manifest or args.proposal).resolve(),
            args.episode,
            output,
        )
        return {
            "output": str(output),
            "episode_id": args.episode,
            "evidence_stories": len(packet["evidence"]),
        }
    if args.command == "validate-script":
        return validate_script(
            Path(args.script).resolve(),
            Path(args.evidence).resolve(),
            config.show_bible_path,
        )
    if args.command == "generate-script":
        evidence_path = Path(args.evidence).resolve()
        packet = json.loads(evidence_path.read_text(encoding="utf-8"))
        episode_id = packet["episode"]["episode_id"]
        output = _path_or_default(
            args.output,
            config.episodes_dir / episode_id / "script.json",
        )
        outline = _path_or_default(
            args.outline,
            config.episodes_dir / episode_id / "outline.json",
        )
        return generate_episode_script(config, evidence_path, outline, output)
    if args.command == "trim-script":
        script_path = Path(args.script).resolve()
        evidence_path = Path(args.evidence).resolve()
        output = _path_or_default(args.output, script_path)
        return trim_episode_script(
            config,
            script_path,
            evidence_path,
            output,
            target_words_min=args.target_min,
            target_words_max=args.target_max,
            plan_path=Path(args.plan).resolve() if args.plan else None,
        )
    if args.command == "polish-script":
        script_path = Path(args.script).resolve()
        output = _path_or_default(args.output, script_path)
        return polish_episode_conversation(
            config,
            script_path,
            Path(args.evidence).resolve(),
            Path(args.cast).resolve(),
            output,
            target_words_min=args.target_min,
            target_words_max=args.target_max,
            max_new_calls=args.max_new_calls,
        )
    if args.command == "prepare-tts":
        script = json.loads(Path(args.script).read_text(encoding="utf-8"))
        episode_id = script["episode_id"]
        output = _path_or_default(
            args.output,
            config.work_dir / "tts" / f"{episode_id}-jobs.jsonl",
        )
        cast_path = _path_or_default(
            args.cast,
            config.episodes_dir / episode_id / "cast.json",
        )
        if args.cast is None:
            create_episode_cast(
                config.voice_roster_path,
                episode_id,
                cast_path,
            )
        count = prepare_tts_jobs(
            Path(args.script).resolve(),
            cast_path,
            output,
            config.audio_dir / "cache" / "tts",
            provider=args.provider,
            model=args.model,
        )
        return {"output": str(output), "jobs": count}
    if args.command == "generate-tts":
        return generate_tts_jobs(
            config,
            Path(args.jobs).resolve(),
            execute=args.execute,
            max_credits=args.max_credits,
            limit=args.limit,
        )
    if args.command == "prepare-voice-audition":
        audition_path = Path(args.audition).resolve()
        audition = json.loads(audition_path.read_text(encoding="utf-8"))
        output = _path_or_default(
            args.output,
            config.work_dir
            / "tts"
            / f"{audition['audition_id']}-jobs.jsonl",
        )
        return prepare_voice_candidate_audition_jobs(
            config,
            audition_path,
            Path(args.candidates).resolve(),
            output,
        )
    if args.command == "prepare-dialogue-audition":
        audition_path = Path(args.audition).resolve()
        audition = json.loads(audition_path.read_text(encoding="utf-8"))
        output = _path_or_default(
            args.output,
            config.work_dir
            / "tts"
            / f"{audition['episode_id']}-dialogue-jobs.jsonl",
        )
        return prepare_dialogue_audition_jobs(
            config,
            audition_path,
            Path(args.cast).resolve(),
            output,
        )
    if args.command == "generate-dialogue-audition":
        return generate_dialogue_audition_jobs(
            config,
            Path(args.jobs).resolve(),
            execute=args.execute,
            max_credits=args.max_credits,
            variant=args.variant,
        )
    if args.command == "prepare-dialogue-episode":
        script_path = Path(args.script).resolve()
        script = json.loads(script_path.read_text(encoding="utf-8"))
        output = _path_or_default(
            args.output,
            config.work_dir
            / "tts"
            / f"{script['episode_id']}-dialogue-episode-jobs.jsonl",
        )
        return prepare_dialogue_episode_jobs(
            config,
            script_path,
            Path(args.cast).resolve(),
            Path(args.performance).resolve(),
            output,
            variant=args.variant,
        )
    if args.command == "generate-dialogue-episode":
        return generate_dialogue_episode_jobs(
            config,
            Path(args.jobs).resolve(),
            execute=args.execute,
            max_credits=args.max_credits,
            limit=args.limit,
        )
    if args.command == "validate-sound-design":
        return validate_sound_design(
            Path(args.sound_design).resolve(),
            Path(args.script).resolve(),
        )
    if args.command == "validate-scene-soundscape":
        return validate_scene_soundscape(
            Path(args.sound_design).resolve(),
            Path(args.visuals).resolve(),
            Path(args.timeline).resolve(),
        )
    if args.command == "prepare-sfx":
        sound_design_path = Path(args.sound_design).resolve()
        sound_design = json.loads(sound_design_path.read_text(encoding="utf-8"))
        output = _path_or_default(
            args.output,
            config.work_dir / "sfx" / f"{sound_design['episode_id']}-jobs.jsonl",
        )
        count = prepare_sfx_jobs(
            sound_design_path,
            Path(args.script).resolve(),
            output,
            config.audio_dir / "cache" / "sfx",
            provider=args.provider,
            model=args.model,
        )
        return {"output": str(output), "jobs": count}
    if args.command == "generate-sfx":
        return generate_sound_effect_jobs(
            config,
            Path(args.jobs).resolve(),
            execute=args.execute,
            max_credits=args.max_credits,
            limit=args.limit,
        )
    if args.command == "render-audio":
        jobs_path = Path(args.jobs).resolve()
        first_job = next(
            json.loads(line)
            for line in jobs_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        output_dir = _path_or_default(
            args.output_dir, config.episodes_dir / first_job["episode_id"] / "audio"
        )
        return render_episode_audio(
            jobs_path,
            config.work_dir,
            output_dir,
            sound_design_path=(
                Path(args.sound_design).resolve() if args.sound_design else None
            ),
            sfx_jobs_path=Path(args.sfx_jobs).resolve() if args.sfx_jobs else None,
        )
    if args.command == "render-dialogue-audio":
        jobs_path = Path(args.jobs).resolve()
        first_job = next(
            json.loads(line)
            for line in jobs_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        output_dir = _path_or_default(
            args.output_dir,
            config.episodes_dir / first_job["episode_id"] / "audio",
        )
        return render_dialogue_episode_audio(
            jobs_path,
            config.work_dir,
            output_dir,
            sound_design_path=(
                Path(args.sound_design).resolve() if args.sound_design else None
            ),
            sfx_jobs_path=(
                Path(args.sfx_jobs).resolve() if args.sfx_jobs else None
            ),
        )
    if args.command == "render-soundscape":
        timeline_path = Path(args.timeline).resolve()
        timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
        output_dir = _path_or_default(
            args.output_dir,
            config.episodes_dir / timeline["episode_id"] / "audio",
        )
        return render_soundscape_audio(
            timeline_path,
            Path(args.sound_design).resolve(),
            config.work_dir,
            output_dir,
            sfx_jobs_path=(
                Path(args.sfx_jobs).resolve() if args.sfx_jobs else None
            ),
            voices_audio_path=(
                Path(args.voices_audio).resolve() if args.voices_audio else None
            ),
        )
    if args.command == "transcript":
        timeline_path = Path(args.timeline).resolve()
        timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
        cast_path = _path_or_default(
            args.cast,
            config.episodes_dir / timeline["episode_id"] / "cast.json",
        )
        speaker_config_path = (
            cast_path if cast_path.is_file() else config.show_bible_path
        )
        output_dir = _path_or_default(
            args.output_dir,
            config.episodes_dir / timeline["episode_id"] / "transcripts",
        )
        paths = render_transcripts(
            timeline_path,
            speaker_config_path,
            output_dir,
            include_sound_cues=not args.speech_only,
            filename_suffix="-voices-only" if args.speech_only else "",
        )
        return {key: str(value) for key, value in paths.items()}
    if args.command == "prepare-visuals":
        timeline_path = Path(args.timeline).resolve()
        timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
        episode_id = str(timeline["episode_id"])
        output = _path_or_default(
            args.output,
            config.episodes_dir
            / episode_id
            / "visuals"
            / f"{episode_id}-visual-scenes.json",
        )
        jobs = _path_or_default(
            args.jobs,
            config.work_dir / "visuals" / f"{episode_id}-prompt-jobs.jsonl",
        )
        return prepare_visual_scenes(
            timeline_path,
            config.catalog_path,
            output,
            jobs,
            min_scene_ms=max(1_000, int(args.min_scene_seconds * 1000)),
            crossfade_ms=max(0, int(args.crossfade_seconds * 1000)),
        )
    if args.command == "expand-visuals":
        return expand_visual_scenes(
            Path(args.source_visuals).resolve(),
            Path(args.timeline).resolve(),
            config.catalog_path,
            Path(args.output).resolve(),
            Path(args.jobs).resolve(),
            min_scene_ms=max(1_000, int(args.min_scene_seconds * 1000)),
            max_scene_ms=max(1_000, int(args.max_scene_seconds * 1000)),
            crossfade_ms=max(0, int(args.crossfade_seconds * 1000)),
        )
    if args.command == "validate-visuals":
        return validate_visual_plan(Path(args.visuals).resolve())
    if args.command == "generate-visual-prompts":
        visuals_path = Path(args.visuals).resolve()
        output_path = (
            Path(args.output).expanduser().resolve() if args.output else None
        )
        return generate_visual_prompt_jobs(
            config,
            Path(args.jobs).resolve(),
            visuals_path,
            output_path=output_path,
            execute=args.execute,
            max_calls=args.max_calls,
            limit=args.limit,
            retry_invalid=args.retry_invalid,
            model=args.model,
            tokenizer_model=args.tokenizer_model,
        )
    if args.command == "import-visual-prompts":
        visuals_path = Path(args.visuals).resolve()
        output_path = (
            Path(args.output).expanduser().resolve() if args.output else None
        )
        return import_visual_prompt_results(
            config,
            Path(args.input).resolve(),
            Path(args.jobs).resolve(),
            visuals_path,
            output_path=output_path,
            model_label=args.model_label,
            tokenizer_model=args.tokenizer_model,
        )
    raise ValueError(f"Unsupported command: {args.command}")


def _path_or_default(value: str | None, default: Path) -> Path:
    return Path(value).expanduser().resolve() if value else default.resolve()


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))
