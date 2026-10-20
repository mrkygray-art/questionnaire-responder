"""FastAPI app for Vercel. POST /api/answer  {"question": "..."}  ->  one answer record."""
from __future__ import annotations

import os
import sys
import time
from collections import defaultdict, deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from responder.agent import DEFAULT_MODEL, answer_question, load_default_kb, make_client  # noqa: E402

MAX_QUESTION_CHARS = 500
HOURLY_LIMIT = int(os.environ.get("HOURLY_LIMIT", "20"))

app = FastAPI(title="Questionnaire Responder", docs_url=None, redoc_url=None)
origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["POST", "GET"], allow_headers=["content-type"])

_hits: dict[str, deque] = defaultdict(deque)  # per server instance only: casual-abuse protection, not a hard limit
_client = make_client()


class Ask(BaseModel):
    question: str = Field(min_length=3, max_length=MAX_QUESTION_CHARS)


def _check_rate(ip: str) -> None:
    now, window = time.time(), _hits[ip]
    while window and now - window[0] > 3600:
        window.popleft()
    if len(window) >= HOURLY_LIMIT:
        raise HTTPException(429, "Hourly limit reached. Please try again later.")
    window.append(now)


@app.get("/api/health")
def health():
    sections, _ = load_default_kb()
    return {"ok": True, "mode": "claude" if _client else "mock", "sections": len(sections)}


@app.post("/api/answer")
def answer(body: Ask, request: Request):
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")).split(",")[0].strip()
    _check_rate(ip)
    try:
        record = answer_question(body.question, client=_client)
    except Exception:  # never leak provider errors or keys to the browser
        raise HTTPException(502, "The answer service is unavailable right now.")
    return {"mode": "claude" if _client else "mock", "model": DEFAULT_MODEL if _client else None, "record": record}


# Local development only: `SERVE_STATIC=1 uvicorn api.index:app --reload` serves the test page at /.
# On Vercel, files in public/ are served by the platform, so this stays off.
if os.environ.get("SERVE_STATIC") == "1":
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "public", html=True), name="static")
