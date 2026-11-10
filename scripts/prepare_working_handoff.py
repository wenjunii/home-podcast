"""Repeatable PRIVATE working-state transfer; dry-run unless --apply is supplied.

The narrow scripts.private_handoff exporter remains available for approved
136-story playback/editing only. Neither command merges receiver installations,
starts models, calls providers, invokes Git, or publishes to GitHub.
"""
from home_podcast.working_handoff import main

if __name__ == "__main__":
    raise SystemExit(main())
