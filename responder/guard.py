"""Prompt-injection guard that runs in code, before the model sees the question.

Rule: instructions aimed at the assistant (or the form's output format) are never obeyed.
They are cut out of the question, quoted back in review_reason, and the record is flagged
for a human. A plain formatting request ("answer in one sentence") is NOT an injection.
"""
from __future__ import annotations

import re

INJECTION_PATTERNS = [
    r"ignore (?:all |any )?(?:previous|prior|above|earlier) (?:instructions|rules|messages)",
    r"\b(?:note|instructions?|message|attention) (?:to|for) (?:the )?(?:ai |llm )?(?:assistants?|models?|llms?|ai)\b",
    r"\bsystem (?:override|prompt|message)\b",
    r"\ball answers (?:on this form )?(?:must|should|need to)\b",
    r"\b(?:mark|set|label|treat) (?:every|all|each) answers?\b",
    r"\bskip (?:all |any )?citations?\b",
    r"\bneeds_human_review\b",
    r"\bconfidence (?:must|should) (?:always )?be\b",
    r"\b(?:do not|don't|never) (?:flag|cite|escalate)\b",
    r"\bdisregard\b.*\b(?:instructions|rules)\b",
]
_COMPILED = [re.compile(p, re.I) for p in INJECTION_PATTERNS]
_SENTENCE_SPLIT = re.compile(r"(?<=[.?!])\s+")
_QUESTION_LABEL = re.compile(r"\bQuestion:\s*", re.I)


def looks_like_injection(text: str) -> bool:
    return any(p.search(text) for p in _COMPILED)


def sanitize(question: str) -> tuple[str, list[str]]:
    """Return (clean_question, injected_spans). Spans are quoted verbatim from the input."""
    q = question.strip()
    injected: list[str] = []

    # "<instruction>. Question: <real question>"
    m = _QUESTION_LABEL.search(q)
    if m:
        prefix, rest = q[: m.start()].strip(), q[m.end():].strip()
        if prefix and looks_like_injection(prefix):
            return (rest or q), [prefix]

    keep: list[str] = []
    for sentence in _SENTENCE_SPLIT.split(q):
        (injected if looks_like_injection(sentence) else keep).append(sentence.strip())
    clean = " ".join(keep).strip()
    return (clean or q), injected


def review_reason(spans: list[str]) -> str:
    quoted = " ".join(f'"{s}"' for s in spans)
    return f"Instruction embedded in the question was ignored: {quoted}"
