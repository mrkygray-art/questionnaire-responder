import pytest
from fastapi.testclient import TestClient

import api.index as web


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    web._hits.clear()
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


def test_rate_limit(monkeypatch):
    monkeypatch.setattr(web, "HOURLY_LIMIT", 2)
    c = TestClient(web.app)
    codes = [c.post("/api/answer", json={"question": "Do you offer an SLA?"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
