"""``python -m jarvis.server`` entry point."""

from __future__ import annotations

import argparse
import logging

from ..config import Config


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the JARVIS web server")
    parser.add_argument("--host", default=None, help="bind address (default: JARVIS_WEB_HOST or 0.0.0.0)")
    parser.add_argument("--port", type=int, default=None, help="port (default: JARVIS_WEB_PORT or 8000)")
    parser.add_argument("--reload", action="store_true", help="auto-reload on code changes (development)")
    args = parser.parse_args()

    settings = Config.from_env()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )

    import uvicorn

    from .app import create_app

    app = create_app(settings)
    uvicorn.run(app, host=args.host or settings.web_host, port=args.port or settings.web_port)


if __name__ == "__main__":
    main()
