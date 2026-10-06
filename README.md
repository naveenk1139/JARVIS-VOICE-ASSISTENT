# J.A.R.V.I.S

**Just A Rather Very Intelligent System** — a modular voice assistant with a browser interface,
a desktop console, and a pluggable skill registry. Talk to it, type to it, or call its HTTP API.

[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-170%20passing-brightgreen.svg)](#testing)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Code style](https://img.shields.io/badge/lint-ruff-261230.svg)](https://docs.astral.sh/ruff/)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-orange.svg)](#contributing)

<img src="jarvis1.jpg" alt="J.A.R.V.I.S" width="100%">

---

## Why this exists

This repository started as a collection of single-file scripts: one for weather, one for
news, one for the dictionary, each with a hardcoded Windows path, placeholder API keys and a
copy of the same `speak()` function. It only ran on the author's laptop, and only with a webcam
plugged in.

JARVIS 2.0 is a rewrite of that idea into something you can actually install, run and extend:

| Before | Now |
| --- | --- |
| `jarvis.py` + 7 loose scripts | one installable package (`jarvis`) |
| Hardcoded `C:\Users\gs935\...` paths | cross-platform config, auto-detection |
| `newsapi.org` placeholder key → always failed | public RSS feeds, no key required |
| Crash without a webcam or a trained face model | face unlock is optional and reports its status |
| Same `speak()` copied into five files | one engine, one service layer |
| Speech only through a microphone | browser UI (Web Speech API), desktop microphone, or typed input |
| `exec(open('youtube_downloader.py').read())` | proper skills with regex intents and tests |
| No tests | 170 tests, no network, microphone or camera needed |

The original scripts are preserved untouched in [`legacy/`](legacy/README.md).

---

## Features

**Everything below works from the browser UI, the desktop console and `jarvis ask`.**

| Skill | What it does | Example |
| --- | --- | --- |
| `weather` | Current conditions and coordinates, via Open-Meteo (no API key needed) | *"What is the weather in Bengaluru?"* |
| `news` | Top headlines from public RSS feeds, spoken and clickable | *"What are the headlines?"* → *"open the second one"* |
| `wikipedia` | Factual answers, with the full article a click away | *"Who is Ada Lovelace?"* |
| `dictionary` | Definitions and spelling, offline corpus first | *"Define serendipity"* |
| `notes` | To-dos and long-term memory that survives restarts | *"Add buy milk to my to-do list"* |
| `time` | Time, date, timers and reminders | *"Remind me in 10 minutes to stretch"* |
| `calculator` | Arithmetic through a safe AST walker (never `eval`) | *"What is 15% of 240?"* |
| `web` | Opens sites, runs searches, shows maps, plays local music | *"Search YouTube for lo-fi beats"* |
| `youtube` | Search links and video metadata | *"youtube lofi hip hop"* |
| `email` | Slot-filled composer over your own SMTP account (opt-in) | *"Send an email to priya@example.com"* |
| `system` | CPU, memory, battery, disk and platform telemetry | *"System status"* |
| `jokes` | Bundled clean joke set, optional online source | *"Tell me a joke"* |
| `smalltalk` | Greetings, identity, persona switching | *"Switch to FRIDAY"* |
| `help` | Self-describing capability list | *"What can you do?"* |
| `goodbye` | Ends the session — it never powers off your computer | *"Go to sleep"* |

**Nice-to-haves**

- Optional LLM fallback (OpenAI-compatible or Anthropic) for questions no skill covers.
- Optional face unlock on the desktop — off by default, and it tells you what is missing
  instead of crashing.
- `jarvis doctor` checks every optional dependency and prints exactly what to install.
- Offline mode (`JARVIS_OFFLINE=true`) for demos, flights and the test suite.

---

## Quickstart

### 1. The browser UI (recommended — no microphone drivers, works on any OS)

```bash
git clone https://github.com/naveenk1139/JARVIS-VOICE-ASSISTENT.git
cd JARVIS-VOICE-ASSISTENT

python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[server]"

jarvis serve
```

Open <http://localhost:8000>, press **Hold to talk** (or hold the space bar), and speak —
or just type. Speech recognition and speech synthesis run in the browser, so there is nothing
else to install.

### 2. The desktop console (microphone + offline text-to-speech)

```bash
pip install -e ".[server,voice,mic,system]"   # Linux also needs: sudo apt install portaudio19-dev espeak-ng

jarvis desktop                # microphone if available, typed input otherwise
jarvis desktop --input text   # force typed input
```

### 3. One-shot commands

```bash
jarvis ask "what is the weather in Pune"
jarvis ask "remind me in 20 minutes to check the oven"
jarvis skills                 # list every registered skill
jarvis doctor                 # environment check
```

> **Windows users:** the old repository shipped a Python 3.8 `PyAudio` wheel. Modern Python
> gets it from PyPI: `pip install "jarvis-assistant[mic]"`.

---

## Configuration

Everything is optional and comes from the environment (or a `.env` file):

```bash
cp .env.example .env
```

The settings you are most likely to change:

```bash
JARVIS_USER_NAME=Aarav              # how the assistant addresses you
JARVIS_LOCATION=Bengaluru           # blank = detect from IP
JARVIS_PERSONA=friday               # feminine voice + FRIDAY persona
JARVIS_MUSIC_DIR=~/Music            # backdrop for "play music"

# Optional: send email (use a Gmail App Password, never your account password)
JARVIS_SMTP_USER=you@gmail.com
JARVIS_SMTP_PASSWORD=xxxx xxxx xxxx xxxx
JARVIS_EMAIL_FROM=you@gmail.com

# Optional: open-ended questions
JARVIS_LLM_API_KEY=sk-...
JARVIS_LLM_PROVIDER=openai          # or "anthropic"; any OpenAI-compatible base URL works
JARVIS_LLM_BASE_URL=http://localhost:11434/v1   # e.g. local Ollama
```

See [docs/CONFIGURATION.md](docs/CONFIGURATION.md) for the complete list.

---

## Architecture

```
                    ┌──────────────────────────────┐
   browser mic ───► │  jarvis/web (HTML + JS UI)   │ ──► POST /api/command
                    └──────────────────────────────┘            │
                                                                ▼
   desktop mic ───► jarvis/voice/listener ──┐        ┌────────────────────────┐
                                            ├──────► │   jarvis/engine.py     │
   stdin / CLI ─────────────────────────────┘        │  match → skill → reply │
                                                     └───────────┬────────────┘
                                                                 │
                                        ┌────────────────────────┴───────────────┐
                                        ▼                                        ▼
                             jarvis/skills/*.py (intents)              jarvis/brains (optional LLM)
                                        │
                                        ▼
                     jarvis/services/*.py — HTTP with retries, caching, offline mode
                     weather · news · wikipedia · dictionary · jokes · system · youtube
```

- **Engine** — owns config, sessions, pending questions and dispatch.
- **Skills** — declare regex intents (`patterns`) and implement `handle()`/`resume()`.
- **Services** — wrap the outside world; every network call has a timeout, retries and a
  friendly failure message.
- **Front doors** — the browser UI, the desktop console and the CLI all speak to the same engine.

Full details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/SKILLS.md](docs/SKILLS.md)

---

## Writing your own skill

```python
# jarvis/skills/coffee.py
from jarvis.models import Match, Response
from jarvis.skills.base import Skill


class CoffeeSkill(Skill):
    name = "coffee"
    description = "Track the office coffee machine."
    priority = 40
    examples = ("Is there coffee left?",)
    patterns = (r"^(?P<check>is there (?:any )?coffee(?: left)?)\b",)

    async def handle(self, match: Match, text: str) -> Response:
        return Response.ok("The pot is half full. Brew more soon.")
```

Register it in `jarvis/skills/__init__.py` and it appears in the UI, the CLI, the help skill
and the API automatically. Intents are plain regex, and each pattern carries a **named group**
so the handler can dispatch on *which* intent matched. See [docs/SKILLS.md](docs/SKILLS.md).

---

## Testing

```bash
pip install -e ".[dev]"
pytest                       # 170 tests, fully offline: no network, mic or camera
pytest --cov=jarvis          # with coverage
ruff check jarvis tests      # lint
```

The suite stubs the HTTP layer, so it is deterministic and CI-safe:

```
tests/test_engine.py      routing, pending questions, timeouts, crash containment
tests/test_skills.py      every skill, from greetings to slot-filled email
tests/test_services.py    HTTP retries, RSS parsing, WMO codes, dictionary fallbacks
tests/test_server.py      every HTTP endpoint through an in-process ASGI client
tests/test_desktop.py     speakers, listeners, wake word, face-unlock status paths
tests/test_storage.py     atomic writes, note lifecycle, bounded history
tests/test_config.py      env parsing, type coercion, .env handling
tests/test_models.py      text normalisation and response serialisation
```

---

## Project layout

```
jarvis/
├── cli.py              jarvis serve | ask | desktop | skills | doctor | weather | train-face
├── engine.py           match an utterance → run a skill → return a Response
├── config.py           environment + .env configuration
├── models.py           Response, Pending, Match, ServiceError, text normalisation
├── context.py          services and stores handed to skills
├── storage.py          notes, reminders, memory, history (atomic JSON writes)
├── skills/             one module per capability
├── services/           weather, news, wikipedia, dictionary, jokes, system, youtube, http
├── brains/             optional LLM fallback (OpenAI-compatible / Anthropic)
├── voice/              speakers, microphones, wake word
├── security/           optional face unlock (OpenCV LBPH)
├── server/             FastAPI app + HTTP API
└── web/                browser UI (plain HTML/CSS/JS — no build step)
legacy/                 the original scripts, preserved for reference
docs/                   architecture, skills, configuration, face unlock, migration
tests/                  the pytest suite
```

---

## API

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | the browser UI |
| `POST` | `/api/command` | `{"text": "...", "session_id": "..."}` → a full response object |
| `GET` | `/api/health` | engine status, skill count, active brain |
| `GET` | `/api/skills` | skill catalog and example phrases |
| `GET` | `/api/session` | pending question and recent transcript |
| `POST` | `/api/reset` | clear a session |
| `GET` | `/api/weather` | structured forecast for the HUD |
| `GET` | `/api/notes` | open notes and remembered facts |
| `GET` | `/api/reminders/due` | reminders that have come due |

Interactive docs: <http://localhost:8000/docs>.
Set `JARVIS_API_TOKEN` to require an `X-JARVIS-Token` header on every API call.

---

## Contributing

Pull requests are very welcome — new skills especially.

1. Fork and branch from `main`.
2. Add your skill in `jarvis/skills/`, register it, add examples.
3. Add tests (they must pass without network access).
4. Run `pytest` and `ruff check jarvis tests`.
5. Open a PR describing the intent patterns you added.

Ideas that would fit well: calendar/ICS integration, Home Assistant control, Spotify playback,
OCR of screenshots, a local Whisper speech backend, a streaming WebSocket UI.

---

## Credits & license

Originally created by [Gaurav Singh](https://github.com/gauravsingh9356) as a hobby assistant,
restructured here into a maintainable application. Released under the [MIT License](LICENSE).
