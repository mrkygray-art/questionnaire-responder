import pytest
from fastapi.testclient import TestClient

import api.index as web
from responder.ratelimit import Limiter


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    monkeypatch.setattr(web, "limiter", Limiter(hourly=20, daily=300))  # memory only, no network
    monkeypatch.setattr(web, "_client", None)  # mock mode, no network


def test_health():
    r = TestClient(web.app).get("/api/health")
    assert r.status_code == 200 and r.json()["sections"] == 39


def test_answer_returns_a_record():
    r = TestClient(web.app).post("/api/answer", json={"question": "Do you support SCIM for automated provisioning?"})
    body = r.json()
    assert r.status_code == 200 and body["mode"] == "mock"
    assert set(body["record"]) >= {"answer", "citations", "confidence", "needs_human_review", "review_reason", "status"}


def test_question_length_is_capped():
    c = TestClient(web.app)
    assert c.post("/api/answer", json={"question": "x" * 501}).status_code == 422
    assert c.post("/api/answer", json={"question": "hi"}).status_code == 422


def test_hourly_limit(monkeypatch):
    monkeypatch.setattr(web, "limiter", Limiter(hourly=2, daily=300))
    c = TestClient(web.app)
    codes = [c.post("/api/answer", json={"question": "Do you offer an SLA?"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_daily_cap_blocks_everyone_and_says_so(monkeypatch):
    monkeypatch.setattr(web, "limiter", Limiter(hourly=20, daily=2))
    c = TestClient(web.app)
    ok = [c.post("/api/answer", json={"question": "Do you offer an SLA?"}, headers={"x-forwarded-for": f"1.1.1.{i}"}).status_code
          for i in range(2)]
    blocked = c.post("/api/answer", json={"question": "Do you offer an SLA?"}, headers={"x-forwarded-for": "9.9.9.9"})
    assert ok == [200, 200] and blocked.status_code == 429 and "today's limit" in blocked.json()["detail"]


def test_health_reports_the_limiter():
    assert TestClient(web.app).get("/api/health").json()["limiter"].startswith("memory")


def test_failures_are_logged_without_the_question(monkeypatch, caplog):
    def boom(*a, **k):
        raise RuntimeError("auth failed")
    monkeypatch.setattr(web, "answer_question", boom)
    r = TestClient(web.app).post("/api/answer", json={"question": "secret question text"})
    assert r.status_code == 502
    assert "RuntimeError: auth failed" in caplog.text and "secret question text" not in caplog.text


def test_rewritten_paths_still_reach_the_right_route():
    c = TestClient(web.app)
    for path in ("/api/index", "/index", "/api"):
        assert c.get(path).json()["ok"] is True                      # GET -> health
        r = c.post(path, json={"question": "Do you support SCIM?"})  # POST -> answer
        assert r.status_code == 200 and "record" in r.json()
    assert c.get("/some/prefix/health").status_code == 200
    assert c.post("/some/prefix/answer", json={"question": "Do you support SCIM?"}).status_code == 200


def test_404_says_which_path_it_saw():
    body = TestClient(web.app).get("/api/nope").json()
    assert body == {"detail": "Not Found", "saw_path": "/api/nope"}
