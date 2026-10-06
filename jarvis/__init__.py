"""J.A.R.V.I.S - a modular voice assistant.

Public API::

    from jarvis import Engine, Config

    engine = Engine(Config.from_env())
    response = await engine.handle("what is the weather in Bengaluru?")
    print(response.text)

The package is deliberately dependency-light: the core engine, skills and the
web server need only ``httpx`` (+ FastAPI for the server). Desktop extras such
as text-to-speech, microphone input, face unlock and screenshots live behind
optional imports and are only loaded when you use them.
"""

from __future__ import annotations

__version__ = "2.0.0"
__all__ = ["Config", "Engine", "Response", "__version__"]


def __getattr__(name: str):  # lazy so `import jarvis` stays cheap
    if name == "Config":
        from .config import Config

        return Config
    if name == "Engine":
        from .engine import Engine

        return Engine
    if name == "Response":
        from .models import Response

        return Response
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
