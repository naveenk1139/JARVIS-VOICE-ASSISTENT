"""Wikipedia and dictionary skills."""

from __future__ import annotations

from ..models import Match, Pending, Response, ServiceError
from .base import Skill


class WikipediaSkill(Skill):
    name = "wikipedia"
    description = "Answer factual questions from Wikipedia and offer the full article."
    requires_network = True
    priority = 60
    examples = ("Who is Ada Lovelace?", "Tell me about black holes", "Search Wikipedia for quantum computing")
    patterns = (
        r"^(?P<explicit>(?:search|look ?up|find|check) (?:on |in )?wikipedia (?:for |about )?(?P<topic>.+))\b",
        r"^(?P<explicit>wikipedia (?P<topic>.+))\b",
        r"^(?P<question>who (?:is|was|are|were) (?P<topic>.+))\b",
        r"^(?P<question>tell me about (?P<topic>.+))\b",
        r"^(?P<question>what (?:is|are|was|were) (?P<topic>.+))\b",
        r"^(?P<question>give me (?:some )?information (?:on|about) (?P<topic>.+))\b",
    )

    #: Topics we deliberately leave to other skills.
    _HANDOFFS = ("weather", "news", "headline", "time", "date", "joke", "note", "reminder")

    async def handle(self, match: Match, text: str) -> Response:
        topic = match.group("topic").strip(" ?.!,")
        if not topic or any(word in topic.lower() for word in self._HANDOFFS):
            return Response.error(
                "I am not sure which subject you mean. Try 'tell me about the solar system'."
            )
        try:
            answer = await self.ctx.wikipedia.lookup(topic)
        except ServiceError as exc:
            return Response.error(str(exc), data={"service": "wikipedia"})
        return Response.ok(
            f"According to Wikipedia, {answer.extract}",
            kind="text",
            data={"wikipedia": answer.to_dict()},
            url=answer.url,
            pending=Pending(skill=self.name, slot="open_article", prompt="Should I open the article?"),
        )

    async def resume(self, pending: Pending, text: str) -> Response:
        if pending.slot != "open_article":
            return Response.error("I did not understand that.")
        lowered = text.lower()
        if any(word in lowered for word in ("yes", "yeah", "sure", "ok", "open", "please")):
            return Response.ok("Opening the article now.", data={"action": "open_last_url"})
        if any(word in lowered for word in ("no", "nope", "nah", "later")):
            return Response.ok("Very well. Ask me anything else.")
        # treat it as a brand new question about the same theme
        try:
            answer = await self.ctx.wikipedia.lookup(text)
        except ServiceError as exc:
            return Response.error(str(exc))
        return Response.ok(
            f"According to Wikipedia, {answer.extract}", data={"wikipedia": answer.to_dict()}, url=answer.url
        )


class DictionarySkill(Skill):
    name = "dictionary"
    description = "Define or spell a word, using a bundled corpus plus a free online dictionary."
    priority = 55
    examples = ("Define serendipity", "What does ubiquitous mean?", "Spell entrepreneur")
    patterns = (
        r"^(?P<define>define|definition of|meaning of)\s+(?P<word>[a-z][a-z'-]*)\b",
        r"^(?P<define>what does)\s+(?P<word>[a-z][a-z'-]*)\s+(?:mean|means)\b",
        r"^(?P<define>dictionary)\s+(?P<word>[a-z][a-z'-]*)\b",
        r"^(?P<spell>how do you spell)\s+(?P<word>[a-z][a-z'-]*)\b",
        r"^(?P<spell>spell)\s+(?P<word>[a-z][a-z'-]*)\b",
    )

    async def handle(self, match: Match, text: str) -> Response:
        word = match.group("word").strip()
        if "spell" in match.groups:
            return Response.ok(
                " ".join(word.upper()) + ".", data={"word": word, "spelling": list(word.upper())}
            )

        try:
            definition = await self.ctx.dictionary.define(word)
        except ServiceError as exc:
            suggestions = self.ctx.dictionary.suggest(word)
            hint = f" Did you mean {', '.join(suggestions)}?" if suggestions else ""
            return Response.error(f"{exc}.{hint}", data={"suggestions": suggestions})

        return Response.ok(
            definition.spoken(),
            kind="text",
            data=definition.to_dict(),
            pending=Pending(
                skill=self.name,
                slot="confirm_definition",
                prompt="Was that the word you meant?",
            ),
        )

    async def resume(self, pending: Pending, text: str) -> Response:
        lowered = text.lower().strip()
        if any(word in lowered for word in ("no", "nope", "not", "wrong")):
            return Response.ok("My apologies. Spell the word for me and I will look again.")
        if any(word in lowered for word in ("yes", "yeah", "correct", "right", "thanks")):
            return Response.ok("Glad that helped.")
        if len(lowered.split()) != 1:
            return Response.ok(
                "Give me a single word to look up, for example: define serendipity.",
            )
        try:
            definition = await self.ctx.dictionary.define(text)
        except ServiceError as exc:
            return Response.error(str(exc))
        return Response.ok(definition.spoken(), data=definition.to_dict())
