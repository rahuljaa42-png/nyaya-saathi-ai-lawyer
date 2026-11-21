"""Citation guard: no legal reference reaches the user unless the knowledge base backs it.

LLMs invent sections, acts and judgments with total confidence. Instead of trusting a prompt,
we scan every outgoing message for anything that looks like a legal citation and remove those
not listed in the 'cites' of the KB entries the model was given.
"""
from __future__ import annotations

import re

PATTERNS = [
    ("section", re.compile(r"\b(?:section|sec\.?|s\.|u/s\.?)\s*\d+[A-Z]?(?:\s*\(\s*\w+\s*\))*", re.I)),
    ("section", re.compile(r"धारा\s*\d+[A-Z]?(?:\s*\(\s*\w+\s*\))*")),
    ("article", re.compile(r"\b(?:article|art\.)\s*\d+[A-Z]?", re.I)),
    ("article", re.compile(r"अनुच्छेद\s*\d+")),
    ("rule", re.compile(r"\brule\s*\d+[A-Z]?(?:\s*\(\s*\w+\s*\))*", re.I)),
    ("act", re.compile(r"\b(?:[A-Z(][A-Za-z().&'-]*\s+){1,8}(?:Act|Code|Rules|Sanhita|Adhiniyam)(?:,)?\s*(?:of\s+)?\d{4}")),
    ("acronym", re.compile(r"\b(?:IPC|CrPC|CPC|BNS|BNSS|BSA|IT Act|NI Act)\b(?:\s*(?:section|sec\.?|s\.)?\s*\d+[A-Z]?)?")),
    ("case", re.compile(r"\b[A-Z][\w&]*\.?(?:\s+[A-Z][\w&]*\.?){0,5}\s+(?:v\.|vs\.?|versus)\s+[A-Z][\w&]*(?:\s+[A-Z][\w&]*){0,4}")),
]


def _norm(s: str) -> str:
    s = s.lower().replace("sec.", "section").replace("u/s", "section").replace("s.", "section ")
    s = re.sub(r"\(.*?\)", "", s)                  # Section 17(2) -> section 17
    return re.sub(r"[\s,.]+", " ", s).strip()


def _allowed(ref: str, kind: str, allowed: list[str]) -> bool:
    if kind == "case":
        return False   # we never cite judgments: the KB has none
    n = _norm(ref)
    allow = [_norm(a) for a in allowed]
    if kind == "section" and ref.strip().startswith("धारा"):
        n = "section " + re.sub(r"\D", " ", ref).split()[0]
    if kind == "article" and ref.strip().startswith("अनुच्छेद"):
        n = "article " + re.sub(r"\D", " ", ref).split()[0]
    return any(n == a or n.endswith(a) or a.endswith(n) and len(n) > 8 for a in allow)


ACT_AFTER = re.compile(r"^\s*(?:\(\w+\)\s*)*(?:of|under|,)?\s*(?:the\s+)?((?:[A-Z(][A-Za-z().&'-]*\s+){1,8}"
                       r"(?:Act|Code|Rules)(?:,)?\s*\d{4})")


def check(text: str, allowed: list[str], pairs: list[tuple[str, str]] | None = None) -> tuple[str, list[dict]]:
    """Return (clean_text, removed). Unbacked references are replaced in place.
    pairs = (act, section) combinations the KB backs; a section named with a different act is removed."""
    removed = []
    spans = []
    for kind, pat in PATTERNS:
        for m in pat.finditer(text):
            ok = _allowed(m.group(0), kind, allowed)
            if ok and kind == "section" and pairs:
                act = ACT_AFTER.match(text[m.end():m.end() + 120])
                if act:
                    sec = _norm(m.group(0))
                    ok = any(_norm(a) == _norm(act.group(1)) and _norm(sc) == sec for a, sc in pairs)
            if not ok:
                spans.append((m.start(), m.end(), kind, m.group(0)))
    spans.sort()
    out, last = [], 0
    for s, e, kind, ref in spans:
        if s < last:
            continue
        out.append(text[last:s])
        out.append("[unverified legal reference removed]")
        removed.append({"kind": kind, "text": ref})
        last = e
    out.append(text[last:])
    return "".join(out), removed
