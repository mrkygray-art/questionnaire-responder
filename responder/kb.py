"""Knowledge base loading and keyword retrieval (BM25, no embeddings, no vector DB).

Each markdown file in kb/ starts with "# Document Name". Every section starts with
"## ID Title", for example "## SEC-2.1 Encryption in transit". Section IDs are what the
agent cites, and what the scorer checks.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ID_RE = re.compile(r"[A-Z]{3}-\d+(?:\.\d+)?")
HEADING_RE = re.compile(r"^##\s+([A-Z]{3}-\d+(?:\.\d+)?)\s*(.*)$")

STOPWORDS = set(
    "a an and are as at be by can could do does for from have how i if in is it its of on or our "
    "please so that the their there these this to us we what when which who will with you your "
    "northgate describe".split()
)

# Questionnaire wording rarely matches policy wording. These expansions bridge the gap.
SYNONYMS = {
    "sla": ["uptime", "availability", "contractual", "service", "level", "agreement"],
    "uptime": ["availability", "sla"],
    "byok": ["customer-managed", "keys"],
    "bring": ["customer-managed", "byok"],
    "eu": ["united", "states", "regions", "hosting"],
    "europe": ["united", "states", "regions", "hosting"],
    "host": ["hosted", "hosting", "regions"],
    "ports": ["port", "firewall", "inbound"],
    "firewall": ["inbound", "port"],
    "dedicated": ["single-tenant", "multi-tenant", "deployment"],
    "instance": ["deployment", "tenant", "multi-tenant"],
    "shared": ["multi-tenant", "tenant"],
    "fingerprints": ["biometric"],
    "fingerprint": ["biometric"],
    "facial": ["biometric"],
    "templates": ["biometric"],
    "rto": ["recovery", "objective"],
    "rpo": ["recovery", "objective"],
    "recovery": ["rto", "rpo"],
    "delete": ["deleted", "deletion", "backup", "retained"],
    "termination": ["contract", "deleted", "retained"],
    "terminate": ["contract", "deleted"],
    "alarm": ["intrusion", "panel"],
    "intrusion": ["alarm"],
    "video": ["vms", "video", "management"],
    "vms": ["video", "management"],
    "rate": ["limit", "api"],
    "pen": ["penetration"],
    "pentest": ["penetration", "test"],
    "attach": ["report", "summary", "letter", "nda"],
    "pre-registration": ["visitor", "pre-registration"],
    "visitor": ["pre-registration"],
    "sso": ["single", "sign-on", "saml", "openid"],
    "mfa": ["multi-factor", "authentication"],
    "multi-factor": ["mfa"],
    "scim": ["provisioning", "user"],
    "roles": ["role", "predefined", "owner", "viewer"],
    "retain": ["retained", "retention"],
    "retention": ["retained", "retain"],
    "logs": ["log", "audit", "event"],
    "backups": ["backup"],
    "soc": ["soc"],
    "iso": ["iso", "27001"],
    "compliant": ["certification", "certified", "hold"],
    "compliance": ["certification", "certified", "hold"],
    "certified": ["certification", "hold"],
    "encrypted": ["encryption", "encrypted"],
    "encryption": ["encrypted"],
    "support": ["support", "hours", "priority"],
}


def _stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9][a-z0-9\-\.]*[a-z0-9]|[a-z0-9]", text.lower())
    return [_stem(w) for w in words if w not in STOPWORDS]


@dataclass(frozen=True)
class Section:
    id: str
    doc: str
    title: str
    text: str

    @property
    def label(self) -> str:
        """Display label used in citations, e.g. 'Security Policy SEC-2.1'."""
        return f"{self.doc} {self.id}"


def load_kb(path: str | Path) -> list[Section]:
    sections: list[Section] = []
    for md in sorted(Path(path).glob("*.md")):
        doc, cur_id, cur_title, buf = md.stem.replace("_", " ").title(), None, "", []

        def flush():
            if cur_id:
                sections.append(Section(cur_id, doc, cur_title, " ".join(buf).strip()))

        for line in md.read_text(encoding="utf-8").splitlines():
            if line.startswith("# ") and not line.startswith("## "):
                doc = line[2:].strip()
                continue
            m = HEADING_RE.match(line)
            if m:
                flush()
                cur_id, cur_title, buf = m.group(1), m.group(2).strip(), []
            elif cur_id and line.strip() and not line.startswith(">"):
                buf.append(line.strip())
        flush()
    ids = [s.id for s in sections]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"Duplicate section IDs in knowledge base: {sorted(dupes)}")
    return sections


class Retriever:
    """BM25 over section title + text, with a small synonym expansion on the query."""

    def __init__(self, sections: list[Section], k1: float = 1.5, b: float = 0.75):
        self.sections = sections
        self.k1, self.b = k1, b
        self.docs = [Counter(tokenize(f"{s.title} {s.title} {s.text}")) for s in sections]
        self.lengths = [sum(c.values()) for c in self.docs]
        self.avg_len = sum(self.lengths) / max(len(self.lengths), 1)
        df: Counter = Counter()
        for c in self.docs:
            df.update(c.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def expand(self, query: str) -> list[str]:
        raw = re.findall(r"[a-z0-9][a-z0-9\-\.]*[a-z0-9]|[a-z0-9]", query.lower())
        extra = [w for r in raw for w in SYNONYMS.get(r, [])]
        return tokenize(" ".join(raw)) + [_stem(w) for w in extra]

    def search(self, query: str, k: int = 8, min_score: float = 0.0) -> list[tuple[Section, float]]:
        terms = self.expand(query)
        scored = []
        for sec, doc, length in zip(self.sections, self.docs, self.lengths):
            score = 0.0
            for t in terms:
                f = doc.get(t, 0)
                if not f:
                    continue
                denom = f + self.k1 * (1 - self.b + self.b * length / self.avg_len)
                score += self.idf.get(t, 0.0) * f * (self.k1 + 1) / denom
            if score > min_score:
                scored.append((sec, score))
        scored.sort(key=lambda p: p[1], reverse=True)
        return scored[:k]
