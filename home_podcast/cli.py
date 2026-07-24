from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .analysis import export_analysis_packets, import_story_cards
from .audio import render_episode_audio
from .catalog import catalog_status
from .config import ProjectConfig
from .doctor import run_doctor
from .ingest import ingest_exports
from .planning import create_month_proposal, lock_episode_manifest, prepare_script_packet
from .script import prepare_tts_jobs, validate_script
from .transcripts import render_transcripts


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
    export.add_argument("--output", help="Output JSONL path")
    export.add_argument("--limit", type=int)
    export.add_argument("--include-existing", action="store_true")

    import_cards = subparsers.add_parser(
        "import-cards", help="Import model-produced story cards from JSONL"
    )
    import_cards.add_argument("input", help="Story-card JSONL path")
    import_cards.add_argument("--analyzer", required=True)
    import_cards.add_argument("--analyzer-version", required=True)

    plan = subparsers.add_parser(
        "plan", help="Create a maximum-coverage thematic proposal for a crawl month"
    )
    plan.add_argument("--month", required=True)
    plan.add_argument("--output", help="Proposal JSON path")

    lock = subparsers.add_parser(
        "lock-episode", help="Freeze one proposed installment as an episode manifest"
    )
    lock.add_argument("--proposal", required=True)
    lock.add_argument("--episode", required=True)

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

    tts = subparsers.add_parser(
        "prepare-tts", help="Create cached, segment-level TTS jobs from a valid script"
    )
    tts.add_argument("--script", required=True)
    tts.add_argument("--output", help="TTS jobs JSONL path")
    tts.add_argument("--provider", required=True)
    tts.add_argument("--model", required=True)

    audio = subparsers.add_parser(
        "render-audio", help="Normalize and assemble completed TTS clips"
    )
    audio.add_argument("--jobs", required=True)
    audio.add_argument("--output-dir", help="Episode audio output directory")

    transcript = subparsers.add_parser(
        "transcript", help="Render Markdown, WebVTT, and SRT from an audio timeline"
    )
    transcript.add_argument("--timeline", required=True)
    transcript.add_argument("--output-dir", help="Transcript output directory")
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
    if args.command == "plan":
        output = _path_or_default(
            args.output, config.work_dir / "planning" / f"{args.month}-proposal.json"
        )
        proposal = create_month_proposal(config, args.month, output)
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
    if args.command == "prepare-tts":
        script = json.loads(Path(args.script).read_text(encoding="utf-8"))
        output = _path_or_default(
            args.output,
            config.work_dir / "tts" / f"{script['episode_id']}-jobs.jsonl",
        )
        count = prepare_tts_jobs(
            Path(args.script).resolve(),
            config.show_bible_path,
            output,
            config.audio_dir / "cache",
            provider=args.provider,
            model=args.model,
        )
        return {"output": str(output), "jobs": count}
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
        return render_episode_audio(jobs_path, config.work_dir, output_dir)
    if args.command == "transcript":
        timeline_path = Path(args.timeline).resolve()
        timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
        output_dir = _path_or_default(
            args.output_dir,
            config.episodes_dir / timeline["episode_id"] / "transcripts",
        )
        paths = render_transcripts(timeline_path, config.show_bible_path, output_dir)
        return {key: str(value) for key, value in paths.items()}
    raise ValueError(f"Unsupported command: {args.command}")


def _path_or_default(value: str | None, default: Path) -> Path:
    return Path(value).expanduser().resolve() if value else default.resolve()


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))
