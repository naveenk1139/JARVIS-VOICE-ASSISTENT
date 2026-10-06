# Architecture

```
   ┌────────────────────┐   ┌───────────────────────┐   ┌──────────────────┐
   │  Browser UI        │   │  Desktop console      │   │  CLI / HTTP API  │
   │  Web Speech API    │   │  pyttsx3 + PyAudio    │   │  scripts, curl   │
   └─────────┬──────────┘   └───────────┬───────────┘   └────────┬─────────┘
             │  POST /api/command       │  engine.handle(text)     │
             └───────────────┬──────────┴──────────────────────────┘
                             ▼
                    ┌──────────────────┐
                    │   Engine         │  sessions · pending questions · persona
                    └────────┬─────────┘
                             ▼
                    ┌──────────────────┐        ┌───────────────────────┐
                    │  Skill registry  │───────►│  Brain (optional LLM) │
                    └────────┬─────────┘        └───────────────────────┘
                             ▼
                    ┌──────────────────┐        ┌───────────────────────┐
                    │  Skills          │───────►│  Services (HTTP)      │
                    └────────┬─────────┘        └───────────────────────┘
                             ▼
                    ┌──────────────────┐
                    │  Stores (JSON)   │
                    └──────────────────┘
```

## Layers

### `jarvis/engine.py`
The only place that decides *what happens next*.

1. Normalise the utterance (`jarvis.models.normalize`) — strip filler like *"hey jarvis"*,
   *"please"*, trailing punctuation, collapse whitespace.
2. If a skill asked a question last turn (`session.pending`), let that skill answer it —
   unless the user clearly started a new command, or the slot is marked `free_text`.
3. Otherwise ask the registry for the best matching skill and run it.
4. Otherwise ask the brain (an LLM when configured, otherwise a friendly "I do not know
   that yet" that suggests real examples).
5. Record both sides of the exchange in the session history and apply side-effect actions
   (`set_persona`, `open_last_url`).

Every skill call runs inside `asyncio.wait_for(...)`, so a hung socket produces a spoken
apology instead of a frozen user interface.

### `jarvis/skills/`
A skill is a class with:

| Attribute | Meaning |
| --- | --- |
| `name` | unique identifier, also shown as a chip in the UI |
| `description` | one line used by `help` and the docs |
| `patterns` | regex intents, each with a **named group** that identifies the intent |
| `examples` | phrases shown as suggestions |
| `priority` | lower wins when several skills match (see below) |
| `requires_network` | documentation flag; useful when running offline |

Priority bands in the default set:

| Band | Skills | Rationale |
| --- | --- | --- |
| 1–15 | `help`, `goodbye`, `about`, `calculator` | unambiguous, must not be shadowed |
| 20–40 | `weather`, `news`, `time`, `countdown`, `smalltalk` | explicit requests |
| 42–60 | `system`, `notes`, `email`, `web`, `wikipedia`, `dictionary`, `jokes` | broader patterns |

`NEW_COMMAND_PRIORITY` (60) defines when a new utterance may interrupt an open question from a
different skill. Slots marked `free_text=True` (an email body) always win, because their content
is arbitrary.

### `jarvis/services/`
Anything that touches the outside world lives here, so skills stay testable:

- `http.py` — one shared `HttpClient` with timeouts, retries on 429/5xx, transport errors
  turned into `ServiceError`, and an `offline` switch.
- `weather.py` — Open-Meteo geocoding + forecast, WMO code translation, IP-based fallback.
- `news.py` — RSS/Atom parsing with `xml.etree`, de-duplication, a 10-minute cache, and an
  optional newsapi.org backend.
- `wikipedia.py` — search + summary REST endpoints, topic cleaning, sentence trimming.
- `dictionary.py` — the bundled 4 MB corpus (lazy loaded) plus dictionaryapi.dev fallback.
- `jokes.py`, `system.py`, `youtube.py` — small, focused wrappers.

Every service raises `ServiceError`; the engine turns that into words the user hears.

### `jarvis/storage.py`
`NoteStore`, `ReminderStore` and `MemoryStore` write JSON atomically (temp file +
`os.replace`), so an interrupted write cannot corrupt user data. `History` is an in-memory,
bounded transcript per session.

### Front doors
- **Web** (`jarvis/server`, `jarvis/web`) — FastAPI endpoints plus a dependency-free HTML/CSS/JS
  UI. The browser performs speech recognition and synthesis; the server only exchanges JSON.
- **Desktop** (`jarvis/desktop.py`, `jarvis/voice`, `jarvis/security`) — microphone input,
  offline TTS, optional wake word and optional face unlock. Each dependency is imported lazily
  and degrades gracefully.
- **CLI** (`jarvis/cli.py`) — `serve`, `ask`, `desktop`, `skills`, `doctor`, `weather`,
  `train-face`, `unlock`, `version`.

## Request lifecycle

```
POST /api/command {"text": "remind me in 5 minutes to stretch"}
  └─ engine.handle()
       ├─ normalize()                       -> "remind me in 5 minutes to stretch"
       ├─ registry.match()                  -> TimeSkill (priority 30)
       ├─ TimeSkill.handle()                -> parse_duration() -> ReminderStore.add()
       └─ Response(text=..., data={...})    -> JSON back to the browser
```

## Design decisions

- **Regex intents, not ML.** Deterministic, instant, no model download, and every pattern is
  readable in review. The optional LLM brain covers everything else.
- **Named groups for dispatch.** `if "date" in match.groups` beats re-parsing the regex
  string, and it makes the intent list self-documenting.
- **Async everywhere in the engine.** Network calls never block the UI thread; the desktop
  listener runs in a worker thread so the event loop stays responsive.
- **Optional everything.** Core install is `httpx` only. Speech, camera, browser and telemetry
  are extras, and `jarvis doctor` tells you what is missing.
- **Failures are conversational.** `ServiceError` becomes a sentence, never a traceback.
- **Never destructive.** `goodbye` ends a session; it does not `poweroff`, and no skill
  executes arbitrary shell commands from an utterance.
