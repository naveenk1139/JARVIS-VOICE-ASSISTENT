"""Arithmetic skill.

Expressions are evaluated through a tiny AST walker rather than :func:`eval`,
so a malicious utterance can never reach the interpreter.
"""

from __future__ import annotations

import ast
import operator
import re

from ..models import Match, Response
from .base import Skill

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}

_WORDS = {
    "plus": "+",
    "added to": "+",
    "minus": "-",
    "less": "-",
    "times": "*",
    "multiplied by": "*",
    "multiply by": "*",
    "into": "*",
    "divided by": "/",
    "over": "/",
    "by": "/",
    "percent of": "/100*",
    "modulo": "%",
    "mod": "%",
    "to the power of": "**",
    "squared": "**2",
}

_ALLOWED_CHARS = re.compile(r"^[\d\s.+\-*/%()^]+$")


def evaluate(expression: str) -> float:
    """Safely evaluate a numeric expression. Raises ``ValueError`` if invalid."""
    cleaned = expression.replace("^", "**").strip()
    if not cleaned or not _ALLOWED_CHARS.match(cleaned):
        raise ValueError(f"unsupported expression: {expression!r}")
    try:
        tree = ast.parse(cleaned, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"that is not a valid expression: {expression!r}") from exc
    return float(_eval_node(tree.body))


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return float(node.value)
        raise ValueError("only numbers are allowed")
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left, right = _eval_node(node.left), _eval_node(node.right)
        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)) and right == 0:
            raise ValueError("division by zero")
        return float(_BIN_OPS[type(node.op)](left, right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return float(_UNARY_OPS[type(node.op)](_eval_node(node.operand)))
    raise ValueError("unsupported operation")


def verbal_to_symbols(text: str) -> str:
    """``"12 times 9"`` -> ``"12 * 9"``."""
    lowered = f" {text.lower()} "
    for word in sorted(_WORDS, key=len, reverse=True):
        lowered = lowered.replace(f" {word} ", f" {_WORDS[word]} ")
    return re.sub(r"\s+", " ", lowered).strip()


class CalculatorSkill(Skill):
    name = "calculator"
    description = "Do arithmetic safely, including percentages and powers."
    priority = 15
    examples = ("Calculate 12 times 9", "What is 15% of 240?", "What is 2 to the power of 10?")
    patterns = (
        r"^(?P<calc>calculate|compute|work out)\s+(?P<expr>.+)$",
        r"^(?P<calc>what(?:'s| is)|how much is)\s+(?P<expr>[\d\s.+\-*/%()^]+(?:plus|minus|times|divided by|multiplied by|mod)?[\d\s.+\-*/%()^A-Za-z]*)$",
        r"^(?P<calc>add|subtract|multiply|divide)\s+(?P<expr>.*\d.*)$",
        r"^(?P<calc>\d+(?:\.\d+)?\s*(?:\+|-|\*|/|times|plus|minus|divided by|multiplied by)\s*\d+(?:\.\d+)?.*)$",
    )

    async def handle(self, match: Match, text: str) -> Response:
        raw = match.group("expr").strip(" ?.!")
        expression = verbal_to_symbols(_fix_percent(raw))

        if not any(char.isdigit() for char in expression):
            return Response.error("I need at least one number to calculate with.")

        try:
            result = evaluate(expression)
        except (ValueError, SyntaxError, OverflowError) as exc:
            return Response.error(f"I could not calculate that expression ({exc}).")

        pretty = f"{result:,.10g}"
        if float(result).is_integer():
            pretty = f"{int(result):,}"
        return Response.ok(
            f"{raw} is {pretty}.",
            kind="text",
            data={"expression": expression, "result": result, "formatted": pretty},
        )


def _fix_percent(text: str) -> str:
    """``15% of 240`` -> ``15/100*240``."""
    return re.sub(r"(\d+(?:\.\d+)?)\s*%\s*of\s*", r"\1/100*", text)
