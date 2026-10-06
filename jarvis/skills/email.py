"""Email skill.

Sending is *opt-in*: it requires SMTP credentials in the environment. When they
are missing the skill explains exactly what to configure instead of pretending
to send mail (which is what the legacy script's placeholder credentials did).

The conversation is slot-filled and stored on the :class:`~jarvis.models.Pending`
object, so the draft survives between utterances: recipient -> subject -> body ->
confirmation -> delivery.
"""

from __future__ import annotations

import asyncio
import logging
import re
import smtplib
from email.message import EmailMessage
from typing import Any

from ..models import Match, Pending, Response, ServiceError
from .base import Skill

log = logging.getLogger(__name__)

_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", re.IGNORECASE)
_CANCEL = ("cancel", "discard", "drop it", "forget it", "stop")
_CONFIRM = ("send", "yes", "yeah", "ok", "okay", "go ahead", "deliver", "do it")


class EmailSkill(Skill):
    name = "email"
    description = "Compose and send email through your own SMTP account (opt-in)."
    priority = 48
    settings = ("JARVIS_SMTP_USER", "JARVIS_SMTP_PASSWORD", "JARVIS_EMAIL_FROM")
    examples = ("Send an email to priya@example.com", "Email the team about the release")
    patterns = (
        r"^(?P<send>send (?:an? )?(?:email|mail)|email|mail)"
        r"(?:\s+to\s+(?P<recipient>[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}))?"
        r"(?:\s+(?:about|saying|regarding|that)\s+(?P<subject>.+))?$",
        r"^(?P<send>send (?:an? )?(?:email|mail))\s+(?P<recipient_named>[a-z][a-z ]{1,30})\s+"
        r"(?:about|saying|regarding)\s+(?P<subject>.+)$",
    )

    # ------------------------------------------------------------------ handle
    async def handle(self, match: Match, text: str) -> Response:
        if not self.ctx.config.email_enabled:
            return Response.error(
                "Email is not configured yet. Add JARVIS_SMTP_USER, JARVIS_SMTP_PASSWORD and "
                "JARVIS_EMAIL_FROM to your .env file, restart me, and I will send mail for you.",
                data={"setting": "JARVIS_SMTP_USER", "configured": False},
            )

        recipient = match.group("recipient").strip()
        if not recipient and "recipient_named" in match.groups:
            name = match.group("recipient_named").strip()
            stored = self.ctx.memory.recall(f"email {name}") or self.ctx.memory.recall(name)
            if stored and _EMAIL.search(stored):
                recipient = _EMAIL.search(stored).group(0)  # type: ignore[union-attr]
            else:
                return Response.ok(
                    f"What is the email address for {name}?",
                    pending=Pending(self.name, "recipient", data={"subject": match.group("subject").strip()}),
                )

        if recipient:
            subject = match.group("subject").strip()
            if subject:
                return Response.ok(
                    f"What should the email to {recipient} say?",
                    pending=Pending(
                        self.name, "body", data={"to": recipient, "subject": subject}, free_text=True
                    ),
                )
            return Response.ok(
                f"What is the subject of the email to {recipient}?",
                pending=Pending(self.name, "subject", data={"to": recipient}),
            )

        return Response.ok(
            "Who should I send it to? Give me an email address.",
            pending=Pending(self.name, "recipient"),
        )

    # ------------------------------------------------------- multi-turn dialogue
    async def resume(self, pending: Pending, text: str) -> Response:
        answer = text.strip()
        draft = dict(pending.data or {})

        if pending.slot == "recipient":
            found = _EMAIL.search(answer)
            if not found:
                return Response.error("That does not look like an email address. Try again, please.")
            draft["to"] = found.group(0)
            if draft.get("subject"):
                return Response.ok(
                    f"What should the email to {draft['to']} say?",
                    pending=Pending(self.name, "body", data=draft, free_text=True),
                )
            return Response.ok(
                f"Got it, {draft['to']}. What is the subject?",
                pending=Pending(self.name, "subject", data=draft),
            )

        if pending.slot == "subject":
            draft["subject"] = answer
            return Response.ok(
                "And what should the message say?",
                pending=Pending(self.name, "body", data=draft, free_text=True),
            )

        if pending.slot == "body":
            draft["body"] = answer
            preview = f"To {draft.get('to')}, subject '{draft.get('subject')}', message: {answer}"
            return Response.ok(
                f"Ready to send. {preview}. Say 'send' to confirm or 'cancel' to drop it.",
                pending=Pending(self.name, "confirm", data=draft),
            )

        if pending.slot == "confirm":
            lowered = answer.lower()
            if any(word in lowered for word in _CANCEL):
                return Response.ok("Dropped the draft. Nothing was sent.")
            if any(word in lowered for word in _CONFIRM):
                return await self._deliver(draft)
            return Response.error("Say 'send' to deliver the email or 'cancel' to drop it.")

        return Response.error("I lost track of that email. Please start again.")

    # ----------------------------------------------------------------- delivery
    async def _deliver(self, draft: dict[str, Any]) -> Response:
        cfg = self.ctx.config
        to = str(draft.get("to", "")).strip()
        if not _EMAIL.fullmatch(to):
            return Response.error("I do not have a valid recipient address. Let us start over.")

        message = build_message(
            sender=cfg.email_from or cfg.smtp_user,
            to=to,
            subject=str(draft.get("subject", "")),
            body=str(draft.get("body", "")),
        )
        sender = EmailSender(
            host=cfg.smtp_host, port=cfg.smtp_port, user=cfg.smtp_user, password=cfg.smtp_password
        )
        try:
            await sender.send_async(message)
        except ServiceError as exc:
            return Response.error(f"I could not send that email: {exc}", data={"service": "email"})
        return Response.ok(f"Email sent to {to}.", data={"sent": {"to": to, "subject": message["Subject"]}})


def build_message(*, sender: str, to: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = to
    message["Subject"] = subject or "(no subject)"
    message.set_content(body)
    return message


class EmailSender:
    """Synchronous SMTP delivery, executed in a worker thread."""

    def __init__(self, *, host: str, port: int, user: str, password: str) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password

    def send(self, message: EmailMessage) -> None:
        try:
            with smtplib.SMTP(self.host, self.port, timeout=20) as server:
                server.ehlo()
                server.starttls()
                server.login(self.user, self.password)
                server.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            log.warning("SMTP delivery failed: %s", exc)
            raise ServiceError(f"the mail server rejected the message ({exc})", service="email") from exc

    async def send_async(self, message: EmailMessage) -> None:
        await asyncio.to_thread(self.send, message)
