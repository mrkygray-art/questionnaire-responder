"""FastAPI app for Vercel. POST /api/answer  {"question": "..."}  ->  one answer record."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from responder.agent import DEFAULT_MODEL, answer_question, load_default_kb, make_client  # noqa: E402
from responder.ratelimit import LimitExceeded, Limiter  # noqa: E402

MAX_QUESTION_CHARS = 500

log = logging.getLogger("responder")

app = FastAPI(title="Questionnaire Responder", docs_url=None, redoc_url=None)


class NormalizePath:
    """Vercel can hand the app the rewritten path (/api/index) instead of the one the browser asked for.
    Map every form back to the two real routes, so it works either way: a path ending in /answer or
    /health maps to that route, and a bare /api or /api/index maps by method (POST answers, GET is health)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope["path"].rstrip("/") or "/"
            tail = path.rsplit("/", 1)[-1]
            if tail in ("answer", "health"):
                new = f"/api/{tail}"
            elif path in ("/api", "/api/index", "/index"):
                new = "/api/answer" if scope["method"] == "POST" else "/api/health"
            else:
                new = scope["path"]
            if new != scope["path"]:
                scope = dict(scope, path=new, raw_path=new.encode())
        await self.app(scope, receive, send)


origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["POST", "GET"], allow_headers=["content-type"])

app.add_middleware(NormalizePath)


@app.exception_handler(404)
async def not_found(request: Request, exc):
    return JSONResponse({"detail": "Not Found", "saw_path": request.url.path}, status_code=404)


limiter = Limiter.from_env()  # shared Redis counters when configured, else this instance's memory
_client = make_client()


class Ask(BaseModel):
    question: str = Field(min_length=3, max_length=MAX_QUESTION_CHARS)


@app.get("/api/health")
def health():
    sections, _ = load_default_kb()
    return {"ok": True, "mode": "claude" if _client else "mock", "sections": len(sections), "limiter": limiter.status()}


@app.post("/api/answer")
def answer(body: Ask, request: Request):
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")).split(",")[0].strip()
    try:
        limiter.check(ip)
    except LimitExceeded as exc:
        raise HTTPException(429, exc.message)
    try:
        record = answer_question(body.question, client=_client)
    except Exception as exc:  # never leak provider errors or keys to the browser
        # The log gets the error type and a short message (never the question) so Vercel's runtime logs explain failures.
        log.error("answer failed: %s: %s", type(exc).__name__, str(exc)[:300])
        raise HTTPException(502, "The answer service is unavailable right now.")
    return {"mode": "claude" if _client else "mock", "model": DEFAULT_MODEL if _client else None, "record": record}


# Local development only: `SERVE_STATIC=1 uvicorn api.index:app --reload` serves the test page at /.
# On Vercel, files in public/ are served by the platform, so this stays off.
if os.environ.get("SERVE_STATIC") == "1":
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "public", html=True), name="static")
