# Writing a skill

A skill teaches JARVIS one capability. It declares regex intents and implements the handler
for them. Everything else — matching, prioritisation, error handling, timeouts, history,
session follow-ups — is handled by the engine.

## Minimal skill

```python
# jarvis/skills/coffee.py
from jarvis.models import Match, Response
from jarvis.skills.base import Skill


class CoffeeSkill(Skill):
    name = "coffee"
    description = "Report how much coffee is left in the pot."
    priority = 40
    requires_network = False
    examples = ("Is there coffee left?", "Coffee status")

    patterns = (r"^(?P<check>is there (?:any )?coffee(?: left)?|coffee status)\b",)

    async def handle(self, match: Match, text: str) -> Response:
        return Response.ok("The pot is about half full.")
```

Register it in `jarvis/skills/__init__.py`:

```python
from .coffee import CoffeeSkill

DEFAULT_SKILLS = (
    ...
    CoffeeSkill,
)
```

The skill now appears in the browser UI suggestions, `jarvis skills`, `/api/skills` and the
`help` skill.

## The intent convention

Every pattern carries a **named group** naming the intent, and the handler dispatches on that
group's presence:

```python
patterns = (
    r"^(?P<status>coffee status|is there coffee)\b",
    r"^(?P<brew>brew (?:a )?(?P<cups>\d+) cups?)\b",
)

async def handle(self, match, text):
    if "brew" in match.groups:
        cups = int(match.group("cups"))
        return Response.ok(f"Brewing {cups} cups.")
    return Response.ok("The pot is half full.")
```

Notes:

- Patterns are compiled with `re.IGNORECASE` and matched with `search`, so anchor with `^` when
  the phrase must start the utterance.
- Groups that take part in the match but are empty (a marker group such as `(?P<status>)`) are
  still present in `match.groups`, so `"status" in match.groups` works.
- `match.group("cups", default="1")` never raises on a missing group.

## Asking a follow-up question

Return a `Pending` describing the question; the engine routes the user's next utterance back to
your skill's `resume()`:

```python
from jarvis.models import Pending

async def handle(self, match, text):
    return Response.ok(
        "Which roast?",
        pending=Pending(skill=self.name, slot="roast", prompt="Roast?"),
    )

async def resume(self, pending: Pending, text: str) -> Response:
    if pending.slot == "roast":
        return Response.ok(f"Brewing a {text.strip()} roast.")
    return Response.error("I lost track of that.")
```

Multi-slot dialogues (like `email`) accumulate values in `pending.data` and rebuild the
`Pending` each turn. Mark a slot `free_text=True` when the answer can look like any other
command — an email body, for example — so a coincidental skill match cannot steal the turn.

## Return values

| Helper | Use it for |
| --- | --- |
| `Response.ok(text, data={...})` | a normal spoken answer |
| `Response.link(text, url)` | anything the user should open (the UI renders a button) |
| `Response.error(text)` | a failure the user should hear, e.g. a service outage |
| `kind="list"` with `data={"headlines": [...]}` | list results the UI renders as items |
| `kind="exit"` | end the session |

`data` is passed through to every front door verbatim — use it for structured extras such as
coordinates, headlines, note objects or `{"action": "set_persona", "persona": "friday"}`.

## Priority and conflicts

Lower `priority` wins when several skills match the same utterance. Follow these bands:

| Range | Use for | Examples |
| --- | --- | --- |
| 1–15 | unambiguous commands | `help`, `goodbye`, `calculator` |
| 20–40 | explicit requests | `weather`, `news`, `time`, `smalltalk` |
| 42–70 | broad or overlapping patterns | `notes`, `web`, `wikipedia`, `dictionary` |
| 80+ | last-resort matchers | fallbacks |

A new utterance can interrupt an open question from a *different* skill when the new match has
`priority <= NEW_COMMAND_PRIORITY` (60 in `jarvis/engine.py`). Keep overlapping skills above
that number.

## Using services and stores

Skills get an `AppContext` as `self.ctx`:

```python
weather = await self.ctx.weather.current("Mumbai")   # service (network)
self.ctx.notes.add("buy milk")                       # store (disk, atomic)
self.ctx.memory.remember("wifi", "hunter2")          # persistent key/value
self.ctx.history.recent(5)                           # this session's transcript
self.ctx.registry.all()                              # introspect other skills
```

Add a new external dependency as a service in `jarvis/services/` and expose it as a property on
`AppContext`, so it can be stubbed in tests.

## Error handling

Raise `ServiceError` for anything environmental (timeouts, HTTP failures, offline mode).
The engine converts it into a spoken message and marks the response as `kind="error"`.
Never let an exception escape `handle()` — but if one does, the engine contains it and logs a
traceback rather than crashing the session.

## Testing your skill

```python
def test_coffee_skill(engine):                      # engine fixture from tests/conftest.py
    response = run(engine.handle("is there coffee left"))
    assert response.skill == "coffee"
    assert "half full" in response.text
```

Tests must not touch the network. Use the `stub_http` fixture to provide canned API payloads,
or the `offline_engine` fixture for offline behaviour. See `tests/test_skills.py` for examples
covering follow-up tracking, service failures and delivery of side effects.

## Checklist

- [ ] `name`, `description`, `priority`, `examples` and `patterns` are set.
- [ ] Every pattern has a unique named intent group.
- [ ] `handle()` is `async` and returns a `Response`.
- [ ] External calls go through a service; failures raise `ServiceError`.
- [ ] Registered in `jarvis/skills/__init__.py`.
- [ ] Tests added, no network access required.
- [ ] `pytest` and `ruff check jarvis tests` pass.
