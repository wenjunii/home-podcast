from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .analysis import export_analysis_packets, import_story_cards
from .audio import render_episode_audio
from .casting import create_episode_cast
from .catalog import catalog_status
from .config import ProjectConfig
from .doctor import run_doctor
from .dialogue_runner import (
    generate_dialogue_audition_jobs,
    prepare_dialogue_audition_jobs,
)
from .editor import trim_episode_script
from .ingest import ingest_exports
from .planning import create_month_proposal, lock_episode_manifest, prepare_script_packet
from .planning import snapshot_crawl_month
from .polisher import polish_episode_conversation
from .provider_runner import analyze_story_jobs
from .script import prepare_tts_jobs, validate_script
from .script_runner import generate_episode_script
from .sfx_runner import generate_sound_effect_jobs
from .sound_design import prepare_sfx_jobs, validate_sound_design
from .transcripts import render_transcripts
from .tts_runner import generate_tts_jobs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="home-podcast",
        description="Incremental production pipeline for the Recovered Homes podcast.",
    )
    parser.add_argument("--config", default="podcast.json", help="Path to podcast.json")
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

    import_cards = subparsers.add_parser(
        "import-cards", help="Import model-produced story cards from JSONL"
    )
    import_cards.add_argument("input", help="Story-card JSONL path")
    import_cards.add_argument("--analyzer", required=True)
    import_cards.add_argument("--analyzer-version", required=True)

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
        "--title",
        help="Override the title when the proposal contains exactly one episode",
    )
    plan.add_argument("--output", help="Proposal JSON path")

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

    validate_sound = subparsers.add_parser(
        "validate-sound-design",
        help="Validate a sound-design cue sheet against its episode script",
    )
    validate_sound.add_argument("--sound-design", required=True)
    validate_sound.add_argument("--script", required=True)

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

    transcript = subparsers.add_parser(
        "transcript", help="Render Markdown, WebVTT, and SRT from an audio timeline"
    )
    transcript.add_argument("--timeline", required=True)
    transcript.add_argument("--output-dir", help="Transcript output directory")
    transcript.add_argument(
        "--cast",
        help="Frozen episode cast; defaults to episodes/<episode>/cast.json",
    )
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
        if (
            args.command
            in {"generate-dialogue-audition", "generate-sfx", "generate-tts"}
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
        )
        return {
            "output": str(output),
            "installments": len(proposal["installments"]),
            **proposal["coverage"],
        }
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
    if args.command == "validate-sound-design":
        return validate_sound_design(
            Path(args.sound_design).resolve(),
            Path(args.script).resolve(),
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
        paths = render_transcripts(timeline_path, speaker_config_path, output_dir)
        return {key: str(value) for key, value in paths.items()}
    raise ValueError(f"Unsupported command: {args.command}")


def _path_or_default(value: str | None, default: Path) -> Path:
    return Path(value).expanduser().resolve() if value else default.resolve()


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))
