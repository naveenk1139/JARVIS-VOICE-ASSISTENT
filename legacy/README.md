# Legacy scripts (preserved for reference)

These are the original single-file scripts that shipped with this repository. They are kept so
the history and the original work stay visible, and so anyone who wants to compare behaviour can
read them side by side. **They are not installed, imported or tested by the new package.**

| Legacy file | What it did | Where that lives now |
| --- | --- | --- |
| `jarvis.py` | main loop, voice, routing, face unlock | `jarvis/engine.py`, `jarvis/cli.py`, `jarvis/desktop.py`, `jarvis/security/face_unlock.py` |
| `helpers.py` | `speak`, `takeCommand`, `weather`, `cpu`, screenshots, dictionary | `jarvis/voice/`, `jarvis/services/`, `jarvis/skills/` |
| `diction.py` | dictionary lookup (duplicate of `helpers.translate`) | `jarvis/services/dictionary.py`, `jarvis/skills/knowledge.py` |
| `news.py` | newsapi.org headlines (placeholder key) | `jarvis/services/news.py` (public RSS, no key) |
| `youtube.py` | YouTube search in a browser | `jarvis/skills/web.py`, `jarvis/services/youtube.py` |
| `youtube_downloader.py` | Tkinter `pytube` downloader | not ported (see note below) |
| `amazon.py` | price scraper that emailed on a price drop | not ported (see note below) |
| `OCR.py` | Tesseract OCR over the webcam | not ported (see note below) |
| `data.txt` | the single remembered sentence | `data/memory.json` via `jarvis/storage.py` |
| `PyAudio-0.2.11-cp38-cp38-win_amd64.whl` | Windows/Python 3.8 wheel | `pip install "jarvis-assistant[mic]"` |

## Why three scripts were not ported

- **`youtube_downloader.py`** bundled a GUI Tkinter app that imported on load (`main.mainloop()`
  at import time) and depended on a `pytube` API that has since changed repeatedly. Downloading
  copyrighted media also needs an explicit, separate decision from the user. The new repo keeps
  YouTube *search* and *opening* only.
- **`amazon.py`** executed scrapes at import time, targeted a single hardcoded product URL, used
  placeholder credentials and would break as soon as Amazon changed its markup.
- **`OCR.py`** required a hardcoded Windows Tesseract path and blocked the main thread in an
  infinite webcam loop. Screenshot/OCR belongs in a separate, explicitly installed extra.

If you want any of these back, they make excellent community pull requests — see the
"Contributing" section of the main [README](../README.md).

## Running the legacy code

It still runs on the machine it was written for (Windows, Python 3.8, webcam, the
`Face-Recognition/` folder and a newsapi key in `news.py`). From the repository root:

```bash
pip install -r ../requirements.txt        # the modern core, for reference
cd legacy && python jarvis.py
```

Expect the original failure modes: hardcoded Windows paths, `engine.setProperty('voice', ...)`
failing on machines without two voices, and a crash if `./Face-Recognition/trainer/trainer.yml`
is missing. That behaviour is exactly what the rewrite fixes — see the table in the main README.
