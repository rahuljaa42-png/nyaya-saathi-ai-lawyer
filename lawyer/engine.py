"""Offline engine: works with no API key and cannot hallucinate law.

Flow: messy story -> case file (facts, dates, amounts, evidence, gaps) -> triage (code)
-> where you stand (KB entries only) -> options -> a draft document -> when to get a lawyer.
The LLM engine reuses every piece of this and only adds understanding + language.
"""
from __future__ import annotations

import datetime as dt
import re

from . import kb, triage
from .guard import check

TODAY = dt.date(2026, 11, 21)

EVIDENCE = {
    "deposit": [("rent agreement", r"agreement|anubandh|अनुबंध|एग्रीमेंट"),
                ("proof you paid the deposit (receipt / bank or UPI transfer)", r"receipt|upi|transfer|bank|paytm|gpay|phonepe|रसीद"),
                ("date you handed back the keys", r"keys?|chabi|चाबी|handed|vacat|khali|ख़ाली|खाली"),
                ("photos or video of the flat when you left", r"photo|video|pic"),
                ("messages with the landlord", r"whatsapp|message|chat|sms|email|मैसेज")],
    "consumer_refund": [("order ID and invoice", r"order|invoice|bill|ऑर्डर|बिल"),
                        ("proof of payment", r"paid|payment|upi|card|bank|भुगतान"),
                        ("screenshots of return / refund status", r"screenshot|status|return|refund"),
                        ("chat or email with customer care", r"chat|email|customer care|support|ticket")],
    "unpaid_salary": [("offer or appointment letter", r"offer|appointment|joining|letter|ऑफ़र|ऑफर|नियुक्ति"),
                      ("salary slips", r"slip|payslip|स्लिप"),
                      ("bank statement showing the last salary received", r"bank|statement|credited|account|बैंक"),
                      ("emails / messages asking for the salary", r"email|mail|message|whatsapp|hr"),
                      ("resignation or termination letter (if any)", r"resign|terminat|relieving|इस्तीफ")],
}

QUESTIONS = {
    "deposit": ["How much was the deposit and when did you pay it?", "On what date did you hand back the keys?",
                "Did the landlord give any reason or list deductions?", "Which state is the flat in?"],
    "consumer_refund": ["Which platform or seller, and what is the order ID?", "How much did you pay, and on what date?",
                        "When did you request the return/refund, and what does the status say?",
                        "Have you written to the platform's Grievance Officer yet?"],
    "unpaid_salary": ["Which months are unpaid, and how much per month?", "Are you still working there, or did you resign / get removed? On what date?",
                      "Is it a private company (not government)?", "Which state do you work in?"],
}

QUESTIONS_HI = {
    "deposit": ["डिपॉज़िट कितना था और कब दिया था?", "आपने चाबी किस तारीख़ को लौटाई?",
                "क्या मकान-मालिक ने कोई कारण या कटौती बताई?", "फ़्लैट किस राज्य में है?"],
    "consumer_refund": ["कौन-सा प्लेटफ़ॉर्म या विक्रेता, और ऑर्डर ID क्या है?", "कितना भुगतान किया और किस तारीख़ को?",
                        "रिटर्न/रिफ़ंड कब माँगा, और स्टेटस क्या दिखा रहा है?", "क्या आपने प्लेटफ़ॉर्म के शिकायत अधिकारी को लिखा है?"],
    "unpaid_salary": ["कौन-से महीनों का वेतन बाक़ी है, और महीने का कितना?", "क्या आप अभी भी वहाँ काम करते हैं, या इस्तीफ़ा/हटाए गए? किस तारीख़ को?",
                      "क्या यह प्राइवेट कंपनी है (सरकारी नहीं)?", "आप किस राज्य में काम करते हैं?"],
}

STEPS = {
    "deposit": [("Collect your proof", "Gather the items in your checklist below, especially proof of payment and the handover date.", []),
                ("Send a written demand", "Send the demand letter below by WhatsApp and email, and by registered post if you can. Ask for the refund within 15 days and for a written list of any deductions.", []),
                ("Check your state's rent law", "Deposit rules depend on your state.", ["R-STATE", "R-MTA"]),
                ("If they still refuse", "Contact free legal aid; a recovery suit in civil court is the formal route.", ["R-SUIT", "LA-NALSA"])],
    "consumer_refund": [("Collect your proof", "Order ID, invoice, payment proof and screenshots of the refund status.", []),
                        ("Write to the Grievance Officer", "Use the platform's Grievance Officer contact (usually in the footer or 'Grievance' page). Keep the complaint number.", ["CP-ECOM"]),
                        ("Register on the National Consumer Helpline", "Free, and companies often respond to it.", ["CP-NCH"]),
                        ("File at the District Consumer Commission", "If there is still no refund, file online.", ["CP-EJAGRITI", "CP-FORUM", "CP-FEE", "CP-LIMIT"])],
    "unpaid_salary": [("Collect your proof", "Offer letter, salary slips, bank statements and messages asking for the salary.", []),
                      ("Send a written demand to HR", "Send the demand letter below by email, with the exact months and amount.", ["W-CODE", "W-DUE", "W-EXIT"]),
                      ("File a wage claim", "If unpaid, file a claim with the wage authority (ask your district labour office who it is).", ["W-CLAIM", "W-RULES"]),
                      ("Get free help", "Free legal aid can help you file.", ["LA-NALSA"])],
}

STEPS_HI = {
    "deposit": ["अपने सबूत इकट्ठा करें", "लिखित माँग भेजें (15 दिन की समय-सीमा)", "अपने राज्य का किराया क़ानून देखें", "फिर भी मना करें तो"],
    "consumer_refund": ["अपने सबूत इकट्ठा करें", "शिकायत अधिकारी को लिखें", "राष्ट्रीय उपभोक्ता हेल्पलाइन पर दर्ज करें", "ज़िला उपभोक्ता आयोग में दाखिल करें"],
    "unpaid_salary": ["अपने सबूत इकट्ठा करें", "HR को लिखित माँग भेजें", "वेतन दावा दायर करें", "मुफ़्त मदद लें"],
}

MONTH = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
HI_MONTHS = {"जनवरी": 1, "फ़रवरी": 2, "फरवरी": 2, "मार्च": 3, "अप्रैल": 4, "मई": 5, "जून": 6, "जुलाई": 7,
             "अगस्त": 8, "सितंबर": 9, "सितम्बर": 9, "अक्टूबर": 10, "नवंबर": 11, "नवम्बर": 11, "दिसंबर": 12, "दिसम्बर": 12}
EN_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
ISSUE_NAMES = {"deposit": ("Security deposit not returned", "सिक्योरिटी डिपॉज़िट वापस नहीं मिला"),
               "consumer_refund": ("Refund or faulty product (consumer)", "रिफ़ंड या ख़राब सामान (उपभोक्ता)"),
               "unpaid_salary": ("Unpaid salary", "बकाया वेतन")}


def parsed_dates(text: str) -> list[dt.date]:
    out = []
    for m in re.finditer(rf"\b(?:(\d{{1,2}})\s+)?{MONTH}\s*,?\s*(\d{{4}})\b", text, re.I):
        out.append(dt.date(int(m.group(3)), EN_MONTHS[m.group(2).lower()[:3]], int(m.group(1) or 1)))
    for name, num in HI_MONTHS.items():
        for m in re.finditer(rf"(?:(\d{{1,2}})\s+)?{name}\s*,?\s*(\d{{4}})", text):
            out.append(dt.date(int(m.group(2)), num, int(m.group(1) or 1)))
    for m in re.finditer(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", text):
        try:
            out.append(dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))))
        except ValueError:
            pass
    return [d for d in out if d <= TODAY]


def extract_dates(text: str) -> list[str]:
    pats = [r"(?:\d{1,2}\s+)?(?:" + "|".join(HI_MONTHS) + r")\s*\d{4}", r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", rf"\b\d{{1,2}}\s+{MONTH}\s*,?\s*\d{{0,4}}\b",
            rf"\b{MONTH}\s+\d{{4}}\b", r"\b(?:last|pichhle|pichle)\s+(?:month|mahine|week|hafte)\b"]
    out = []
    for p in pats:
        out += [m.group(0) for m in re.finditer(p, text, re.I)]
    return out


def months_since(text: str) -> float | None:
    ds = parsed_dates(text)
    if ds:   # the earliest date in the story is taken as when the problem started
        return round((TODAY - min(ds)).days / 30.4, 1)
    t = text.lower()
    m = re.search(r"(\d+|one|two|three|four|five|six|ek|do|teen|char|paanch|chhe)\s*(month|mahine|mahina|महीने|महीना|year|saal|साल|week|hafte)", t)
    if not m:
        return None
    words = {"one": 1, "ek": 1, "two": 2, "do": 2, "three": 3, "teen": 3, "four": 4, "char": 4,
             "five": 5, "paanch": 5, "six": 6, "chhe": 6}
    n = float(words.get(m.group(1), m.group(1)) if not m.group(1).isdigit() else m.group(1))
    unit = m.group(2)
    if unit in ("year", "saal", "साल"):
        n *= 12
    elif unit in ("week", "hafte"):
        n /= 4.3
    return n


def build_case(text: str) -> dict:
    issue, scores = triage.classify(text)
    amts = triage.amounts(text)
    ms = months_since(text)
    flags = triage.red_flags(text) + triage.scope_checks(issue, text, amts, ms)
    ev_have, ev_missing = [], []
    for label, pat in EVIDENCE.get(issue, []):
        (ev_have if re.search(pat, text, re.I) else ev_missing).append(label)
    return {
        "story": text.strip(),
        "language": triage.detect_language(text),
        "issue": issue,
        "issue_scores": scores,
        "amounts_mentioned": amts,
        "dates_mentioned": extract_dates(text),
        "months_since_problem": ms,
        "evidence_mentioned": ev_have,
        "evidence_to_collect": ev_missing,
        "red_flags": flags,
        "in_scope": issue in STEPS and not any(f["code"] in ("danger", "criminal", "court_notice", "family",
                                                             "violence_home", "government", "property",
                                                             "above_district") for f in flags),
    }


def _kb_line(eid: str, lang: str) -> str:
    e = kb.by_id(eid)
    txt = e["hi"] if lang == "hi" else e["en"]
    caution = f" _({e['caution']})_" if e.get("caution") and lang != "hi" else ""
    return f"{txt}{caution} [{eid}]"


def respond(case: dict) -> dict:
    """Full answer as markdown + the KB ids used, all passed through the guard."""
    lang = "hi" if case["language"] == "hi" else "en"
    issue = case["issue"]
    md = []
    hard = [f for f in case["red_flags"] if f["code"] in ("danger", "violence_home")]
    if hard:
        md.append("### ⚠️ Safety first" if lang == "en" else "### ⚠️ पहले सुरक्षा")
        md += [f"- {f['message']}" for f in hard]
    if not case["in_scope"]:
        md.append("### You should talk to a real lawyer" if lang == "en" else "### आपको किसी असली वकील से बात करनी चाहिए")
        md += [f"- {f['message']}" for f in case["red_flags"]] or [
            "- I only cover three problems: a deposit your landlord won't return, a refund that never came, "
            "and unpaid salary. Your problem looks different, so I won't guess."]
        md.append(_kb_line("LA-NALSA", lang))
        used = ["LA-NALSA"]
        return _finish(md, used, case)

    md.append("### Your case so far" if lang == "en" else "### आपका केस अभी तक")
    en_name, hi_name = ISSUE_NAMES[issue]
    md.append(f"- **Problem:** {hi_name if lang == 'hi' else en_name}")
    if case["amounts_mentioned"]:
        md.append(f"- **Amount mentioned:** ₹{max(case['amounts_mentioned']):,}")
    if case["dates_mentioned"]:
        md.append(f"- **Dates mentioned:** {', '.join(case['dates_mentioned'])}")
    if case["evidence_mentioned"]:
        md.append(f"- **Proof you mentioned:** {', '.join(case['evidence_mentioned'])}")
    md.append("- **Collect if you can:** " + ", ".join(case["evidence_to_collect"]) if case["evidence_to_collect"] else "")
    qs = QUESTIONS_HI[issue] if lang == "hi" else QUESTIONS[issue]
    md.append(("**To make this stronger, tell me:** " if lang == "en" else "**केस मज़बूत करने के लिए बताइए:** ") + " · ".join(qs))
    if case["red_flags"]:
        md.append("### Be careful" if lang == "en" else "### ध्यान दें")
        md += [f"- {f['message']}" for f in case["red_flags"]]

    md.append("### Where you stand and what to do" if lang == "en" else "### आपकी स्थिति और क्या करें")
    used = []
    names_hi = STEPS_HI[issue]
    for k, (title, body, ids) in enumerate(STEPS[issue], 1):
        head = names_hi[k - 1] if lang == "hi" else title
        md.append(f"{k}. **{head}.** {body if lang == 'en' else ''}".rstrip())
        for i in ids:
            md.append(f"    - {_kb_line(i, lang)}")
            used.append(i)
    if "LA-NALSA" not in used:
        md.append(_kb_line("LA-NALSA", lang))
        used.append("LA-NALSA")
    md.append("### Draft you can send" if lang == "en" else "### भेजने के लिए ड्राफ़्ट (अंग्रेज़ी में)")
    md.append("```\n" + draft(case) + "\n```")
    md += lawyer_block(lang)
    return _finish(md, used, case)


def lawyer_block(lang: str) -> list[str]:
    """Fixed text, always added by code (never left to the model)."""
    return ["### When you need a real lawyer" if lang == "en" else "### कब असली वकील चाहिए",
            ("- The other side replies through a lawyer, sends you a notice, or threatens you.\n"
             "- You are near a time limit, or the amount is large for you.\n"
             "- You are not sure the facts above are right. This is general information, not legal advice."
             if lang == "en" else
             "- सामने वाला वकील के ज़रिए जवाब दे, नोटिस भेजे, या धमकी दे।\n- समय-सीमा पास हो, या रक़म आपके लिए बड़ी हो।\n"
             "- यह सामान्य जानकारी है, क़ानूनी सलाह नहीं।"),
            _kb_line("LA-NALSA", lang)]


def _finish(md, used, case):
    items = [kb.by_id(i) for i in dict.fromkeys(used)]
    text = "\n".join(x for x in md if x)
    clean, removed = check(text, kb.allowed_cites(items), kb.cite_pairs(items))
    src = "\n".join(f"- [{e['id']}] " + " · ".join(e["sources"]) for e in items)
    clean += f"\n\n**Sources (checked {kb.verified_on()}):**\n{src}"
    return {"markdown": clean, "kb_used": [e["id"] for e in items], "guard_removed": removed}


def draft(case: dict) -> str:
    issue = case["issue"]
    amt = f"₹{max(case['amounts_mentioned']):,}" if case["amounts_mentioned"] else "₹[AMOUNT]"
    today = TODAY.strftime("%d %B %Y")
    if issue == "deposit":
        return f"""Date: {today}
To: [Landlord's name], [Address of the flat]
Subject: Demand for refund of security deposit of {amt}

I was your tenant at [address] from [start date] to [date keys were handed back].
I paid a security deposit of {amt} on [date] by [cash / bank transfer / UPI, reference].
I handed back vacant possession on [date]. The deposit has not been refunded.

Please refund {amt} to [UPI ID / bank account] within 15 days of this letter.
If you are deducting anything, please send a written, itemised list with reasons and bills.

If I do not receive the refund or a written reply within 15 days, I will take further steps
to recover it, including approaching the legal services authority and the appropriate court.

[Your name] · [Phone] · [Email]
Enclosed: rent agreement, deposit payment proof, handover message/photos"""
    if issue == "consumer_refund":
        return f"""Date: {today}
To: The Grievance Officer, [Platform name]
Subject: Refund not received – Order [ORDER ID]

I placed order [ORDER ID] on [date] and paid {amt} by [mode].
[I returned the item on (date) / The order was cancelled on (date)], and the refund was promised by [date].
As of today the refund has not reached my account.

Please refund {amt} to my original payment method within 7 days and confirm in writing.
If this is not resolved, I will register a grievance with the National Consumer Helpline
and file a complaint before the District Consumer Commission.

[Your name] · [Registered phone/email on the account]
Enclosed: invoice, payment proof, screenshots of the return/refund status"""
    if issue == "unpaid_salary":
        return f"""Date: {today}
To: [HR Manager / Director], [Company name], [Address]
Subject: Payment of pending salary of {amt}

I [work / worked] as [designation] (Employee ID [ID]) since [joining date].
My salary for [months] totalling {amt} has not been paid.
[I resigned on (date) / My employment ended on (date)], and my dues remain unpaid.

Please pay {amt} to my salary account within 7 days and share a statement of my dues.
If it is not paid, I will file a claim before the authority under the Code on Wages, 2019.

[Your name] · [Phone] · [Email]
Enclosed: offer letter, salary slips, bank statement, earlier emails"""
    return "(No draft for this kind of problem.)"
