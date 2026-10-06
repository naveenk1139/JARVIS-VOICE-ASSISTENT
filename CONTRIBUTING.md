# Contributing

Thanks for wanting to help! Bug reports, new skills, better intents and documentation fixes are
all welcome.

## Getting set up

```bash
git clone https://github.com/naveenk1139/JARVIS-VOICE-ASSISTENT.git
cd JARVIS-VOICE-ASSISTENT

python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest                                                # 170 tests, offline, a few seconds
```

Optional extras if you are working on those areas:

```bash
pip install -e ".[server]"     # browser UI / HTTP API
pip install -e ".[voice,mic]"  # text-to-speech + microphone
pip install -e ".[vision]"     # face unlock
```

## Ground rules

1. **Tests must pass without a network connection.** Stub HTTP through the `stub_http` fixture
   (see `tests/conftest.py`). No test may open a socket, microphone or camera.
2. **Optional dependencies stay optional.** Import them inside the function or class that needs
   them and degrade gracefully — `jarvis doctor` should explain what is missing.
3. **Never `eval()` user input**, never `os.system()` an utterance, and never power off a
   machine from a skill.
4. **Failures are conversational.** Raise `ServiceError` for environmental problems; the engine
   turns it into something the user can hear.
5. Run the linters before pushing:

```bash
ruff check jarvis tests
ruff format --check jarvis tests
mypy                       # optional but appreciated
```

## Adding a skill

The step-by-step guide (with the intent/named-group convention and follow-up questions) is in
[docs/SKILLS.md](docs/SKILLS.md). The short version:

1. Create `jarvis/skills/your_skill.py` with a `Skill` subclass.
2. Give every pattern a unique named intent group, and set `examples` so the UI can suggest it.
3. Register it in `jarvis/skills/__init__.py`.
4. Add tests to `tests/test_skills.py`.
5. Update the skills table in `README.md`.

## Adding a service

Anything that talks to the outside world belongs in `jarvis/services/`:

1. Wrap it in a class that takes the `AppContext` (for config and the shared HTTP client).
2. Use `ctx.http` — never `httpx`/`requests` directly — so timeouts, retries and offline mode
   are inherited.
3. Raise `ServiceError` with a `service=` label for any failure.
4. Expose it as a lazily created property on `AppContext`.
5. Test it with `httpx.MockTransport` (see `tests/test_services.py`).

## Pull requests

- Branch from `main`, keep the change focused, and describe the intent patterns you added.
- Include tests and a short note in the PR body about anything user-visible.
- Screenshots help a lot for UI changes.
- By contributing you agree that your work is released under the repository's MIT licence.

## Reporting bugs

Please include: the command you ran, the full output, your OS and Python version, and the
result of `jarvis doctor`. Do not paste API keys or SMTP passwords.
