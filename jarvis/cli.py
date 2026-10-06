"""``jarvis`` command line interface.

jarvis serve                 # browser UI + HTTP API
jarvis ask "what is the weather in Bengaluru"
jarvis desktop               # microphone + speakers console
jarvis skills                # list every capability
jarvis doctor                # environment / configuration check
jarvis train-face ./faces    # train the optional face unlock model
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import logging
import platform
import shutil
import sys
from pathlib import Path

from . import __version__
from .config import Config
from .engine import Engine

log = logging.getLogger("jarvis.cli")

_BANNER = r"""
   _  _   _  _ ___ __   __
  | |/_\ | \| | _ \ \ / /   J.A.R.V.I.S  v{version}
  | |_|_|| .` |   / \ V /    Just A Rather Very Intelligent System
  |_|   |_|\_|_|_\  \_/     engine + skills: run 'jarvis doctor'
"""


def _configure_logging(config: Config, verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_serve(args: argparse.Namespace) -> int:
    config = Config.from_env()
    _configure_logging(config, args.verbose)

    import uvicorn

    from .server.app import create_app

    host = args.host or config.web_host
    port = args.port or config.web_port
    banner = _BANNER.format(version=__version__)
    print(banner)
    print(f"  web UI  : http://localhost:{port}")
    print(f"  API docs: http://localhost:{port}/docs\n")

    # 0.0.0.0 is required for containers/preview proxies; localhost still works.
    proxy_headers = host not in {"127.0.0.1", "localhost"}
    uvicorn.run(
        create_app(config),
        host=host,
        port=port,
        log_level=("debug" if args.verbose else config.log_level.lower()),
        proxy_headers=proxy_headers,
        forwarded_allow_ips="*" if proxy_headers else None,
    )
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    config = Config.from_env()
    _configure_logging(config, args.verbose)

    async def run() -> int:
        engine = Engine(config)
        try:
            response = await engine.handle(args.text, session_id="cli")
        finally:
            await engine.aclose()
        if args.json:
            print(json.dumps(response.to_dict(), indent=2))
        else:
            print(response.text)
            if response.url:
                print(response.url)
        return 0 if response.kind != "error" else 1

    return asyncio.run(run())


def cmd_desktop(args: argparse.Namespace) -> int:
    config = Config.from_env()
    _configure_logging(config, args.verbose)
    print(_BANNER.format(version=__version__))

    from .desktop import run_desktop

    try:
        asyncio.run(run_desktop(config, input_mode=args.input))
    except KeyboardInterrupt:  # pragma: no cover - interactive
        print("\nShutting down.")
    return 0


def cmd_skills(args: argparse.Namespace) -> int:
    config = Config.from_env()

    async def run() -> int:
        engine = Engine(config)
        try:
            catalog = engine.catalog()
            if args.json:
                print(json.dumps(catalog, indent=2))
                return 0
            width = max(len(entry["name"]) for entry in catalog)
            print(_BANNER.format(version=__version__))
            for entry in catalog:
                print(f"  {entry['name']:<{width}}  {entry['description']}")
                for example in entry["examples"][:2]:
                    print(f"  {'':<{width}}    e.g. {example}")
            print(f"\n  {len(catalog)} skills registered.")
        finally:
            await engine.aclose()
        return 0

    return asyncio.run(run())


def cmd_doctor(args: argparse.Namespace) -> int:
    config = Config.from_env()
    print(_BANNER.format(version=__version__))

    checks: list[tuple[str, bool, str]] = []

    checks.append(("Python >= 3.10", sys.version_info >= (3, 10), platform.python_version()))
    checks.append(("httpx (core)", _has("httpx"), "required for all network skills"))
    checks.append(("fastapi (web UI)", _has("fastapi"), "pip install 'jarvis-assistant[server]'"))
    checks.append(("uvicorn (web UI)", _has("uvicorn"), "pip install 'jarvis-assistant[server]'"))
    checks.append(("pyttsx3 (speech out)", _has("pyttsx3"), "pip install 'jarvis-assistant[voice]'"))
    checks.append(
        ("speech_recognition (speech in)", _has("speech_recognition"), "pip install 'jarvis-assistant[mic]'")
    )
    checks.append(("pyaudio (microphone driver)", _has("pyaudio"), "Linux: sudo apt install portaudio19-dev"))
    checks.append(("psutil (system stats)", _has("psutil"), "pip install 'jarvis-assistant[system]'"))
    checks.append(("cv2 (face unlock)", _has("cv2"), "pip install 'jarvis-assistant[vision]'"))

    dictionary = Path(config.dictionary_path)
    checks.append(("dictionary corpus", dictionary.is_file(), str(dictionary)))
    checks.append(("data directory", Path(config.data_dir).is_dir() or True, str(config.data_dir)))
    checks.append(("SMTP configured", config.email_enabled, "JARVIS_SMTP_USER / JARVIS_SMTP_PASSWORD"))
    checks.append(("LLM fallback", bool(config.llm_api_key), "JARVIS_LLM_API_KEY (optional)"))
    checks.append(
        ("Chrome/Chromium binary", bool(_find_browser(config)), config.chrome_path or "auto-detect")
    )

    for label, ok, hint in checks:
        marker = "ok  " if ok else "--  "
        print(f"  [{marker}] {label:<32} {hint}")

    optional = [label for label, ok, _ in checks if not ok]
    print()
    if optional:
        print(f"  {len(optional)} optional check(s) not satisfied - the assistant still runs.")
    else:
        print("  Everything is in place.")

    async def probe() -> None:
        engine = Engine(config)
        try:
            print(f"\n  engine: {engine.describe()}")
        finally:
            await engine.aclose()

    asyncio.run(probe())
    return 0


def cmd_weather(args: argparse.Namespace) -> int:
    config = Config.from_env()

    async def run() -> int:
        engine = Engine(config)
        try:
            keyword = "what is the weather" + (f" in {args.location}" if args.location else "")
            response = await engine.handle(keyword, session_id="cli")
            print(response.text)
            if args.json:
                print(json.dumps(response.data, indent=2))
        finally:
            await engine.aclose()
        return 0

    return asyncio.run(run())


def cmd_train_face(args: argparse.Namespace) -> int:
    from .security.face_unlock import train_faces

    config = Config.from_env()
    count, message = train_faces(
        dataset_dir=args.dataset,
        model_path=args.model or config.face_model_path,
        cascade_path=args.cascade or config.face_cascade_path,
    )
    print(message)
    return 0 if count else 1


def cmd_unlock(args: argparse.Namespace) -> int:
    from .security.face_unlock import FaceUnlock, UnlockStatus

    config = Config.from_env()
    unlocker = FaceUnlock(
        model_path=config.face_model_path,
        cascade_path=config.face_cascade_path,
        owner=config.face_owner_name or config.display_name(),
    )
    result = unlocker.run()
    print(f"[{result.status.value}] {result.message}")
    return 0 if result.status in {UnlockStatus.SUCCESS, UnlockStatus.DISABLED} else 1


def cmd_version(args: argparse.Namespace) -> int:
    print(f"JARVIS {__version__} (python {platform.python_version()} on {platform.platform()})")
    return 0


# --------------------------------------------------------------------------- #
# Helpers / parser
# --------------------------------------------------------------------------- #
def _has(module: str) -> bool:
    try:
        importlib.import_module(module)
        return True
    except Exception:
        return False


def _find_browser(config: Config) -> str | None:
    if config.chrome_path and Path(config.chrome_path).exists():
        return config.chrome_path
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome", "msedge"):
        found = shutil.which(name)
        if found:
            return found
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jarvis", description="J.A.R.V.I.S voice assistant")
    parser.add_argument("--version", action="version", version=f"jarvis {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the web UI and HTTP API")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.set_defaults(func=cmd_serve)

    ask = sub.add_parser("ask", help="send one command and print the answer")
    ask.add_argument("text", help='the command, e.g. "what is the weather in Pune"')
    ask.add_argument("--json", action="store_true", help="print the raw response object")
    ask.set_defaults(func=cmd_ask)

    desktop = sub.add_parser("desktop", help="talk to JARVIS through the microphone")
    desktop.add_argument("--input", choices=["auto", "microphone", "text"], default="auto")
    desktop.set_defaults(func=cmd_desktop)

    skills = sub.add_parser("skills", help="list registered skills")
    skills.add_argument("--json", action="store_true")
    skills.set_defaults(func=cmd_skills)

    doctor = sub.add_parser("doctor", help="check optional dependencies and configuration")
    doctor.set_defaults(func=cmd_doctor)

    weather = sub.add_parser("weather", help="quick weather check")
    weather.add_argument("--location", default="")
    weather.add_argument("--json", action="store_true")
    weather.set_defaults(func=cmd_weather)

    train = sub.add_parser("train-face", help="train the optional face-unlock model")
    train.add_argument("dataset", help="folder of face images (jpg)")
    train.add_argument("--model", default="")
    train.add_argument("--cascade", default="")
    train.set_defaults(func=cmd_train_face)

    unlock = sub.add_parser("unlock", help="test the face-unlock pipeline")
    unlock.set_defaults(func=cmd_unlock)

    version = sub.add_parser("version", help="print version information")
    version.set_defaults(func=cmd_version)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
