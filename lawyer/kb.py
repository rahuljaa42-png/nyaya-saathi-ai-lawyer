"""Verified knowledge base: the only source of legal statements."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

KB_PATH = Path(__file__).resolve().parent.parent / "kb" / "laws.json"


@lru_cache(maxsize=1)
def load() -> dict:
    return json.loads(KB_PATH.read_text(encoding="utf-8"))


def entries(issue: str | None = None) -> list[dict]:
    es = load()["entries"]
    return [e for e in es if issue is None or issue in e["issues"]]


def by_id(i: str) -> dict | None:
    return next((e for e in load()["entries"] if e["id"] == i), None)


def allowed_cites(items: list[dict]) -> list[str]:
    return sorted({c for e in items for c in e.get("cites", [])})


def verified_on() -> str:
    return load()["verified_on"]


def cite_pairs(items: list[dict]) -> list[tuple[str, str]]:
    """(act, section) pairs: 'Section 69' is only valid together with its own Act."""
    out = []
    for e in items:
        acts = [c for c in e.get("cites", []) if not c.lower().startswith(("section", "article", "rule"))]
        secs = [c for c in e.get("cites", []) if c.lower().startswith(("section", "article", "rule"))]
        out += [(a, s) for a in acts for s in secs]
    return out
