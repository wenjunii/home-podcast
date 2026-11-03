"""Run with python -m scripts.private_handoff; no network or model imports.

Transfer packages and historical snapshots are not disposable task copies.
This entry point never prunes them or runs task-completion cleanup. Preserve
production helpers and receipts under work/ even when their names look old.
The separate cleanup policy is documented in AGENTS.md and PORTABLE_SETUP.md.
"""
from home_podcast.private_handoff import main

if __name__ == "__main__":
    raise SystemExit(main())
