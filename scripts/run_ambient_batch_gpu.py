"""Isolated, explicit offline CUDA worker; no automatic model installation."""
import argparse
from pathlib import Path

from home_podcast.ambient_batch import AmbientBatch
from home_podcast.config import ProjectConfig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--brief", required=True)
    parser.add_argument("--max-calls", type=int, required=True)
    args = parser.parse_args()
    runner = AmbientBatch(ProjectConfig.load(args.config), Path(args.brief))
    runner.render(execute=True, max_calls=args.max_calls, worker=True)


if __name__ == "__main__":
    main()
