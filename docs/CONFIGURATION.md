# Configuration

Every setting is optional and can come from either a `.env` file in the project root or a real
environment variable. Precedence: **defaults → `.env` → environment variables**.

```bash
cp .env.example .env
```

## Identity

| Variable | Default | Meaning |
| --- | --- | --- |
| `JARVIS_NAME` | `JARVIS` | Assistant name, used in replies and the UI |
| `JARVIS_USER_TITLE` | `Sir` | Fallback form of address |
| `JARVIS_USER_NAME` | *(empty)* | Your name; wins over the title when set |
| `JARVIS_PERSONA` | `jarvis` | `jarvis` (masculine voice) or `friday` (feminine) |

You can change the persona at runtime: *"switch to FRIDAY"*.

## Location & weather

| Variable | Default | Meaning |
| --- | --- | --- |
| `JARVIS_LOCATION` | *(empty)* | City name; empty = detect from IP |
| `JARVIS_FALLBACK_LOCATION` | `Bengaluru` | Used when detection fails |
| `JARVIS_UNITS` | `metric` | `metric` (°C, km/h) or `imperial` (°F, mph) |

Weather uses [Open-Meteo](https://open-meteo.com) — free, no API key, no account.

## News

| Variable | Default | Meaning |
| --- | --- | --- |
| `JARVIS_NEWS_FEEDS` | Google News India + The Hindu RSS | Comma-separated RSS/Atom URLs |
| `JARVIS_NEWS_SOURCE` | `Google News India` | Label shown with headlines |
| `JARVIS_NEWS_API_KEY` | *(empty)* | Optional newsapi.org key; replaces RSS when set |
| `JARVIS_NEWS_COUNTRY` | `in` | Country code for the newsapi.org backend |

## Storage

| Variable | Default | Meaning |
| --- | --- | --- |
| `JARVIS_DATA_DIR` | `./data` | Notes, reminders, memory and logs |
| `JARVIS_DICTIONARY_PATH` | bundled corpus | Path to a `word → definition` JSON file |

Files written: `notes.json`, `reminders.json`, `memory.json`. Writes are atomic.

## Email (opt-in)

| Variable | Default | Meaning |
| --- | --- | --- |
| `JARVIS_SMTP_HOST` | `smtp.gmail.com` | SMTP server |
| `JARVIS_SMTP_PORT` | `587` | STARTTLS port |
| `JARVIS_SMTP_USER` | *(empty)* | Login user |
| `JARVIS_SMTP_PASSWORD` | *(empty)* | Login password / app password |
| `JARVIS_EMAIL_FROM` | *(empty)* | `From:` address (defaults to the user) |
| `JARVIS_EMAIL_DEFAULT_TO` | *(empty)* | Default recipient |

The email skill stays disabled until **both** `JARVIS_SMTP_USER` and `JARVIS_SMTP_PASSWORD` are
set — it will tell you that instead of pretending to send. For Gmail, create an
[App Password](https://myaccount.google.com/apppasswords); never use your account password.

## Language model (optional)

Adds open-ended answers when no skill matches.

| Variable | Default | Meaning |
| --- | --- | --- |
| `JARVIS_LLM_PROVIDER` | `openai` | `openai` (`/chat/completions`) or `anthropic` (`/v1/messages`) |
| `JARVIS_LLM_API_KEY` | *(empty)* | Enables the brain when set |
| `JARVIS_LLM_MODEL` | `gpt-4o-mini` | Model name |
| `JARVIS_LLM_BASE_URL` | provider default | Any OpenAI-compatible endpoint (Groq, Together, OpenRouter, Ollama…) |
| `JARVIS_LLM_MAX_TOKENS` | `300` | Keep replies short enough to speak |
| `JARVIS_LLM_TEMPERATURE` | `0.4` | Sampling temperature |
| `JARVIS_LLM_SYSTEM_PROMPT` | built-in | Override the assistant's persona prompt |

Local example (Ollama):

```bash
JARVIS_LLM_PROVIDER=openai
JARVIS_LLM_BASE_URL=http://localhost:11434/v1
JARVIS_LLM_MODEL=llama3.1
JARVIS_LLM_API_KEY=ollama        # any non-empty string
```

## Desktop app

| Variable | Default | Meaning |
| --- | --- | --- |
| `JARVIS_CHROME_PATH` | auto-detected | Browser binary used by "open X" on the desktop |
| `JARVIS_VOICE_RATE` | `180` | pyttsx3 speaking rate |
| `JARVIS_VOICE_INDEX_MASCULINE` | `0` | Voice index for the JARVIS persona |
| `JARVIS_VOICE_INDEX_FEMININE` | `1` | Voice index for the FRIDAY persona |
| `JARVIS_WAKE_WORD` | *(empty)* | e.g. `jarvis` — ignore speech until it is heard |
| `JARVIS_MUSIC_DIR` | *(empty)* | Folder of `.mp3`/`.wav` files for "play music" |

List the voices your system offers:

```bash
python -c "import pyttsx3; [print(i, v.name) for i, v in enumerate(pyttsx3.init().getProperty('voices'))]"
```

## Face unlock (optional, desktop)

| Variable | Default | Meaning |
| --- | --- | --- |
| `JARVIS_REQUIRE_FACE_UNLOCK` | `false` | Ask for a face check at startup |
| `JARVIS_FACE_MODEL_PATH` | `Face-Recognition/trainer/trainer.yml` | Trained LBPH model |
| `JARVIS_FACE_CASCADE_PATH` | `Face-Recognition/haarcascade_frontalface_default.xml` | Haar cascade |
| `JARVIS_FACE_OWNER_NAME` | *(empty)* | Name used in the welcome message |

When the model, cascade or camera is missing, the assistant reports the problem and continues
instead of crashing. See [FACE_UNLOCK.md](FACE_UNLOCK.md).

## Server

| Variable | Default | Meaning |
| --- | --- | --- |
| `JARVIS_WEB_HOST` | `0.0.0.0` | Bind address (`0.0.0.0` is needed for containers/preview proxies) |
| `JARVIS_WEB_PORT` | `8000` | Port (`PORT` also works) |
| `JARVIS_API_TOKEN` | *(empty)* | When set, API calls must send `X-JARVIS-Token` |
| `JARVIS_SESSION_TTL_SECONDS` | `14400` | Idle session expiry |
| `JARVIS_HISTORY_LIMIT` | `50` | Transcript turns kept per session |

> ⚠️ Binding to `0.0.0.0` exposes the API to your local network. Set `JARVIS_API_TOKEN` if that
> matters on your network, and never expose the port directly to the internet.

## Behaviour & diagnostics

| Variable | Default | Meaning |
| --- | --- | --- |
| `JARVIS_OFFLINE` | `false` | Never touch the network; keeps the UI and local skills working |
| `JARVIS_SKILL_TIMEOUT` | `25` | Seconds before a skill is abandoned |
| `JARVIS_HTTP_TIMEOUT` / `JARVIS_HTTP_RETRIES` | `10` / `2` | Outbound HTTP policy |
| `JARVIS_LOG_LEVEL` | `INFO` | `DEBUG` for verbose logs |

`jarvis doctor` prints the effective state of every optional dependency and setting.
