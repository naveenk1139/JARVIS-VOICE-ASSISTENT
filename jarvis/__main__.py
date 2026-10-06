"""``python -m jarvis`` runs the CLI, so the package works without installation."""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
