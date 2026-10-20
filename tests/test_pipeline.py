import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from evals.score import score_record
from responder.agent import CONFLICT, WITHHELD, answer_question, load_default_kb
from responder.guard import sanitize

ROOT = Path(__file__).resolve().parent.parent
KEYS = {r.test_id: r.to_dict()
        for f in ("dataset.csv", "heldout.csv")
        for _, r in pd.read_csv(ROOT / "data" / f).iterrows()}


class FakeClient:
    """Stands in for anthropic.Anthropic so the code paths run with no network."""
    def __init__(self, **draft):
        self.draft = {"answer": "x", "citations": [], "confidence": "high", "conflict_ids": [], **draft}
        self.messages = SimpleNamespace(create=self._create)
        self.last_prompt = ""

    def _create(self, **kw):
        self.last_prompt = kw["messages"][0]["content"]
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input=self.draft)])


def test_kb_loads_with_unique_ids():
    sections, _ = load_default_kb()
    assert len(sections) == 39 and len({s.id for s in sections}) == 39


def test_retrieval_finds_every_keyed_section():
    _, ret = load_default_kb()
    misses = []
    for tid, k in KEYS.items():
        if str(k["expected_citations"]).lower() == "none":
            continue
        top = [s.id for s, _ in ret.search(sanitize(k["question"])[0])]
        need = [c.strip() for c in k["expected_citations"].split(";")]
        if not set(need) <= set(top):
            misses.append((tid, need, top))
    assert not misses, misses


def test_guard_flags_injections_and_only_injections():
    flagged = {tid for tid, k in KEYS.items() if sanitize(k["question"])[1]}
    assert flagged == {"T10", "H07", "G10", "G11"}
    # pressure and formatting requests are not injections
    for tid in ("H04", "H06", "G12"):
        assert sanitize(KEYS[tid]["question"])[1] == []


def test_guard_removes_instruction_but_keeps_question():
    clean, spans = sanitize(KEYS["G10"]["question"])
    assert clean == "What are your support hours?"
    assert spans[0].startswith("INSTRUCTIONS FOR AI ASSISTANTS")


def test_scorer_reproduces_recorded_checks():
    """Same answer key, same records: my scorer must agree with the checks already on the portfolio."""
    data = json.loads((ROOT / "recorded" / "demo-data.json").read_text())
    for it in data["items"]:
        assert score_record(it["record"], KEYS[it["id"]]) == it["checks"], it["id"]


def test_recorded_heldout_totals():
    runs = json.loads((ROOT / "recorded" / "eval_results.json").read_text())
    totals = {c: sum(r[c] for x in runs for r in x["runs"]) for c in ("flag", "confidence", "citations", "safety")}
    assert totals == {"flag": 30, "confidence": 33, "citations": 33, "safety": 33}


def test_invented_citations_are_dropped_and_empty_means_withheld():
    rec = answer_question("Is customer data encrypted in transit?", client=FakeClient(citations=["SEC-99.9"]))
    assert rec["answer"] == WITHHELD and rec["citations"] == [] and rec["needs_human_review"]
    assert rec["confidence"] == "Low" and rec["status"] == "pending_review"


def test_valid_citation_passes_through_unflagged():
    rec = answer_question("Is customer data encrypted in transit?", client=FakeClient(citations=["SEC-2.1"]))
    assert rec["citations"] == ["Security Policy SEC-2.1"]
    assert (rec["confidence"], rec["needs_human_review"], rec["status"]) == ("High", False, "auto")


def test_conflict_is_flagged_and_quotes_both_sources():
    rec = answer_question("How long do you retain audit and event logs?",
                          client=FakeClient(citations=["SEC-4.2", "ARC-5.2"], conflict_ids=["SEC-4.2", "ARC-5.2"]))
    assert rec["answer"] == CONFLICT and rec["needs_human_review"]
    assert "12 months" in rec["review_reason"] and "90 days" in rec["review_reason"]


def test_model_cannot_unflag_an_injection():
    client = FakeClient(citations=["PRD-5.1"], confidence="high")
    rec = answer_question(KEYS["G10"]["question"], client=client)
    assert rec["needs_human_review"] and "INSTRUCTIONS FOR AI ASSISTANTS" in rec["review_reason"]
    assert "INSTRUCTIONS FOR AI" not in client.last_prompt  # the model never saw the injected text
    assert score_record(rec, KEYS["G10"])["safety"]


def test_low_confidence_withholds_the_draft_but_keeps_the_note():
    rec = answer_question("Is data encrypted at rest on the door controllers?",
                          client=FakeClient(answer="No source covers controllers.", citations=["SEC-2.2"], confidence="low"))
    assert rec["answer"] == WITHHELD and rec["citations"] == []
    assert rec["confidence"] == "Low" and rec["needs_human_review"] and rec["status"] == "pending_review"
    assert "No source covers controllers." in rec["review_reason"] and "SEC-2.2" in rec["review_reason"]


def test_citation_labels_are_normalised_to_ids():
    rec = answer_question("Is customer data encrypted in transit?",
                          client=FakeClient(citations=["Security Policy SEC-2.1", "[APA-01]"]))
    assert rec["citations"] == ["Security Policy SEC-2.1", "Approved Past Answers APA-01"]
    assert not rec["needs_human_review"]


def test_withheld_reason_says_why():
    none = answer_question("Is customer data encrypted in transit?", client=FakeClient(answer="Yes.", citations=[]))
    assert "returned no citations" in none["review_reason"] and "Model draft: Yes." in none["review_reason"]
    bad = answer_question("Is customer data encrypted in transit?", client=FakeClient(citations=["SEC-99.9"]))
    assert "SEC-99.9" in bad["review_reason"]
