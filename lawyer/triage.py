"""Deterministic triage: what kind of problem, and when to send the person to a real lawyer.

Red flags are decided by code, not by the model, so a persuasive story or a model mistake
cannot talk the assistant out of saying "you need a lawyer / call 112".
Keywords cover English, Hindi (Devanagari) and romanised Hindi (Hinglish).
"""
from __future__ import annotations

import re

ISSUES = {
    "deposit": [r"deposit", r"security", r"advance", r"landlord", r"makaan ?malik", r"malik", r"kiraya",
                r"किराय", r"मकान", r"डिपॉज़िट", r"डिपॉजिट", r"rent", r"flat", r"\bpg\b", r"tenant", r"vacat"],
    "consumer_refund": [r"refund", r"return", r"order", r"amazon", r"flipkart", r"myntra", r"meesho", r"swiggy",
                        r"zomato", r"online", r"defective", r"damaged", r"product", r"seller", r"delivery",
                        r"रिफ़ंड", r"रिफंड", r"सामान", r"ऑर्डर", r"खराब", r"ख़राब", r"paise wapas", r"wapas nahi"],
    "unpaid_salary": [r"salary", r"wage", r"wages", r"tankhwah", r"tankha", r"payment nahi", r"employer", r"\bhr\b",
                      r"company", r"full and final", r"\bf&f\b", r"resign", r"terminated", r"fired", r"stipend",
                      r"वेतन", r"तनख्वाह", r"तनख़्वाह", r"सैलरी", r"नौकरी", r"कंपनी"],
}

RED_FLAGS = [
    ("danger", "You may be in danger. Call 112 (emergency) first.",
     r"\b(kill|murder|attack(ed)?|beat(en|ing)?|hit me|maar(a|ne|enge)|maarpeet|threat(en)?|dhamki|weapon|"
     r"knife|acid)\b|जान से|मारने|धमकी|मारपीट"),
    ("criminal", "This involves police or a crime. Talk to a lawyer or free legal aid before you act.",
     r"\b(police|fir|arrest(ed)?|thana|jail|bail|cheat(ing|ed)?|fraud|420|scam|stolen|chori|"
     r"blackmail|extort)\b|पुलिस|एफ़आईआर|गिरफ़्तार|धोखाधड़ी|चोरी"),
    ("court_notice", "You have received a notice, summons or case. Deadlines may be running: see a lawyer now.",
     r"\b(summons|court (notice|date|case)|case (filed|against me)|legal notice (from|received)|"
     r"notice aaya|notice mila|warrant|hearing)\b|समन|अदालत|कोर्ट"),
    ("family", "Family matters (divorce, custody, maintenance, inheritance) are not covered here.",
     r"\b(divorce|talaq|custody|maintenance|alimony|dowry|dahej|inheritance|will deed|testament|property share|"
     r"husband|wife|in-laws|sasural)\b|तलाक|दहेज|ससुराल|विरासत|वसीयत"),
    ("violence_home", "Domestic violence or harassment needs specialised help. Call 112 if unsafe, or 181 (Women Helpline).",
     r"\b(domestic violence|harass(ment|ed|ing)|sexual|molest|stalk)\b|घरेलू हिंसा|उत्पीड़न"),
    ("government", "Disputes with a government employer or department follow special rules. Talk to a lawyer.",
     r"\b(government (job|employee|department|school|college|hospital|office)|govt\.? (school|job|office|hospital)|sarkari|psu|railway(s)? job|central government employee)\b|सरकारी"),
    ("property", "Disputes over owning land or a house (title, possession, eviction) need a lawyer.",
     r"\b(evict(ion|ed)?|land|plot|title deed|registry|encroach|kabza|possession of (the )?(house|land))\b|"
     r"कब्ज़ा|कब्जा|ज़मीन|जमीन"),
]


def detect_language(text: str) -> str:
    if re.search(r"[ऀ-ॿ]", text):
        return "hi"
    hinglish = r"\b(mera|meri|mujhe|nahi|nahin|kar|raha|rahi|hai|tha|thi|paise|wapas|bol|kya|kaise|abhi|kiya|diya)\b"
    if len(re.findall(hinglish, text.lower())) >= 3:
        return "hinglish"
    return "en"


def classify(text: str) -> tuple[str, dict]:
    t = text.lower()
    scores = {k: sum(len(re.findall(p, t)) for p in pats) for k, pats in ISSUES.items()}
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "unknown", scores
    return best, scores


def red_flags(text: str) -> list[dict]:
    t = text.lower()
    return [{"code": code, "message": msg} for code, msg, pat in RED_FLAGS if re.search(pat, t, re.I)]


AMOUNT_RE = re.compile(r"(?:₹|rs\.?|inr|rupees?)\s*([\d,]+(?:\.\d+)?)\s*(lakh|lac|k|thousand|crore)?"
                       r"|([\d,]+(?:\.\d+)?)\s*(lakh|lac|k|thousand|crore|rupees?|rs\b|रुपये|रुपए|रुपया|रु\.?|लाख|हज़ार|हजार)", re.I)


def amounts(text: str) -> list[int]:
    out = []
    for m in AMOUNT_RE.finditer(text):
        num, unit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        try:
            v = float(num.replace(",", ""))
        except ValueError:
            continue
        unit = (unit or "").lower()
        v *= {"lakh": 1e5, "lac": 1e5, "लाख": 1e5, "k": 1e3, "thousand": 1e3, "हज़ार": 1e3, "हजार": 1e3,
              "crore": 1e7}.get(unit, 1)
        if v >= 50:
            out.append(int(v))
    return out


def scope_checks(issue: str, text: str, amts: list[int], months_since: float | None) -> list[dict]:
    """Issue-specific limits that turn a self-help case into a lawyer case."""
    flags = []
    if issue == "consumer_refund" and amts and max(amts) > 50_00_000:
        flags.append({"code": "above_district", "message": "Above ₹50 lakh the District Commission cannot hear it. Talk to a lawyer."})
    if months_since is not None:
        if issue == "consumer_refund" and months_since > 22:
            flags.append({"code": "time_limit", "message": "You are close to or past the 2-year limit for consumer complaints. Act now and get legal advice."})
        if issue == "unpaid_salary" and months_since > 33:
            flags.append({"code": "time_limit", "message": "You are close to or past the 3-year limit for wage claims. Get legal advice now."})
        if issue == "deposit" and months_since > 33:
            flags.append({"code": "time_limit", "message": "You are close to 3 years since the deposit became due. Courts may treat older claims as time-barred: see a lawyer."})
    return flags
