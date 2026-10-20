"""Run the answer-key questions through the responder and score them.

    python -m evals.run_eval --mode claude --repeats 3 --set all
    python -m evals.run_eval --mode mock                      # no API key, plumbing check only

Writes to evals/out/: eval_results.json (per-run checks), demo-data.json (first run's record per
question, same shape the portfolio replay page reads), and a printed table.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from responder.agent import answer_question, load_default_kb, make_client
from evals.score import score_record

ROOT = Path(__file__).resolve().parent.parent
CHECKS = ("flag", "confidence", "citations", "safety")
SETS = {"tuned": ("Tuned set", ROOT / "data" / "dataset.csv"),
        "heldout": ("Held-out set", ROOT / "data" / "heldout.csv")}


def load_keys(which: str) -> list[tuple[str, dict]]:
    names = list(SETS) if which == "all" else [which]
    rows = []
    for n in names:
        label, path = SETS[n]
        rows += [(label, r.to_dict()) for _, r in pd.read_csv(path).iterrows()]
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["claude", "mock"], default="claude")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--set", choices=["tuned", "heldout", "all"], default="all")
    ap.add_argument("--out", default=str(ROOT / "evals" / "out"))
    args = ap.parse_args()

    client = make_client() if args.mode == "claude" else None
    if args.mode == "claude" and client is None:
        raise SystemExit("ANTHROPIC_API_KEY is not set. Use --mode mock, or export a key.")
    kb = load_default_kb()

    results, items = [], []
    print(f"mode={args.mode}  repeats={args.repeats}\n")
    print(f"{'ID':<6}{'flag':<6}{'conf':<6}{'cite':<6}{'safe':<6}question")
    for label, key in load_keys(args.set):
        runs, first = [], None
        for _ in range(args.repeats):
            rec = answer_question(key["question"], kb=kb, client=client)
            first = first or rec
            sc = score_record(rec, key)
            runs.append(sc)
            if not all(sc.values()):
                print(f"   [{key['test_id']}] failed {[c for c, v in sc.items() if not v]}: {rec['confidence']} "
                      f"review={rec['needs_human_review']} cites={rec['citations']}\n"
                      f"      answer: {rec['answer'][:160]}\n      reason: {rec['review_reason'][:160]}")
        results.append({"id": key["test_id"], "runs": runs})
        cells = []
        for c in CHECKS:
            n = sum(r[c] for r in runs)
            cells.append("ok" if n == len(runs) else f"{n}/{len(runs)}")
        mark = "  <-- check" if any(c != "ok" for c in cells) else ""
        print(f"{key['test_id']:<6}{cells[0]:<6}{cells[1]:<6}{cells[2]:<6}{cells[3]:<6}{key['question'][:52]}{mark}")
        items.append({
            "set": label, "id": key["test_id"], "original": key["question"], "record": first,
            "expected": {"flag": str(bool(key["expected_needs_human_review"])).lower(),
                         "confidence": key["expected_confidence"], "citations": key["expected_citations"]},
            "checks": runs[0],
        })

    full = sum(all(all(r[c] for r in x["runs"]) for c in CHECKS) for x in results)
    by_check = {c: f"{sum(r[c] for x in results for r in x['runs'])}/{sum(len(x['runs']) for x in results)}" for c in CHECKS}
    print(f"\nrows fully passing: {full}/{len(results)}\nby check: {by_check}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "eval_results.json").write_text(json.dumps(results, indent=2))
    (out / "demo-data.json").write_text(json.dumps({"mode": args.mode, "items": items}, indent=2))
    print(f"\nwrote {out}/eval_results.json and demo-data.json")


if __name__ == "__main__":
    main()
