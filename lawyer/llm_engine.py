"""LLM engine: understands any language and messy stories; never the source of law.

The model (1) turns a story into a structured case, (2) explains using ONLY the KB entries
we hand it, citing them as [ID], (3) fills a code-made draft, (4) plays the other side for
practice. Every output goes through guard.check; one retry, then unbacked references are cut.
Red flags from code always win over the model.
"""
from __future__ import annotations

import json
import re

from . import engine, kb, triage
from .guard import check
from .llm import LLM

ISSUE_SET = ["deposit", "consumer_refund", "unpaid_salary", "other"]

INTAKE_SYS = """You help ordinary people in India organise a legal problem. You do not give legal
conclusions here; you only extract facts. Never add facts the person did not say. JSON only."""

INTAKE_USER = """Person's message(s):
\"\"\"{story}\"\"\"

Return JSON:
{{"issue": one of {issues},
 "language": "en" | "hi" | "hinglish" | other ISO code,
 "timeline": [{{"date": "as said, or 'unknown'", "event": "short"}}],
 "other_party": "who they are in dispute with, or 'unknown'",
 "amount_inr": number or null,
 "evidence_have": ["documents/proof they say they have"],
 "evidence_missing": ["proof that would help and they did not mention"],
 "questions": ["max 3 short questions whose answers matter most"],
 "safety_or_crime": true/false (any threat, violence, police, crime),
 "summary": "2 sentences, neutral, in English"}}"""

ANSWER_SYS = """You are Nyaya Saathi, a plain-language legal helper for ordinary people in India.
Rules you must follow:
1. Every legal statement must come from the VERIFIED FACTS list and be tagged with its [ID].
2. Never name any Act, section, rule, article, case or judgment that is not written in those facts.
   If something is not covered, say you don't know and suggest free legal aid.
3. Write in the person's language and register ({language}); Hinglish if they wrote Hinglish.
4. Be short, warm and concrete. Use headings: What happened · Where you stand · What to do next ·
   What to collect · When to get a real lawyer.
5. This is general information, not legal advice. Say so once, at the end."""

ANSWER_USER = """CASE:
{case}

VERIFIED FACTS (the only law you may use):
{facts}

Write the answer."""

RETRY_NOTE = """Your previous answer named legal references that are NOT in the verified facts: {refs}.
Rewrite it without them. Only use the verified facts and their [ID] tags."""

DRAFT_SYS = """You fill in a letter template for an ordinary person in India. Replace a [PLACEHOLDER]
only with facts the person actually gave; leave unknown ones as [PLACEHOLDER]. Do not add any law,
section or threat that is not already in the template. Return JSON: {"letter": "..."}"""

ROLE_SYS = """You are role-playing the {side} in a dispute so that the person can practise.
Case: {summary}
Stay in character: realistic, a bit evasive or stubborn, as such people often are. Push back with
the excuses they commonly give. Never state laws or sections. Keep replies to 2–4 sentences.
After your reply, add a line starting with 'COACH:' giving the person one tip on how to respond
firmly and politely (no law citations)."""


class Lawyer:
    def __init__(self, llm: LLM):
        self.llm = llm

    def intake(self, story: str) -> dict:
        case = engine.build_case(story)          # rules first: red flags, amounts, dates
        data = self.llm.chat_json(INTAKE_SYS, INTAKE_USER.format(story=story, issues=ISSUE_SET), tag="intake",
                                  mock_fn=lambda u: {"issue": case["issue"] if case["issue"] in ISSUE_SET else "other",
                                                     "language": case["language"], "timeline": [], "questions": [],
                                                     "safety_or_crime": False, "summary": "mock"})
        llm_issue = data.get("issue") if data.get("issue") in ISSUE_SET else "other"
        if case["issue"] == "unknown" or (max(case["issue_scores"].values()) <= 1 and llm_issue != "other"):
            case["issue"] = llm_issue if llm_issue != "other" else "unknown"
        case["llm"] = data
        if data.get("safety_or_crime") and not any(f["code"] in ("danger", "criminal") for f in case["red_flags"]):
            case["red_flags"].append({"code": "llm_safety", "message": "The story mentions a threat, violence or police. "
                                      "If you are in danger call 112; for anything criminal, talk to a lawyer."})
        case["language"] = data.get("language") or case["language"]
        if data.get("amount_inr") and not case["amounts_mentioned"]:
            case["amounts_mentioned"] = [int(data["amount_inr"])]
        hard = ("danger", "criminal", "court_notice", "family", "violence_home", "government", "property",
                "above_district", "llm_safety")
        case["in_scope"] = case["issue"] in engine.STEPS and not any(f["code"] in hard for f in case["red_flags"])
        return case

    def answer(self, case: dict) -> dict:
        if not case["in_scope"]:
            return engine.respond(case)           # out of scope: fixed, safe referral text
        items = kb.entries(case["issue"])
        facts = "\n".join(f"[{e['id']}] {e['en']}" + (f" (Caution: {e['caution']})" if e.get("caution") else "")
                          for e in items)
        brief = {k: case.get(k) for k in ("issue", "amounts_mentioned", "dates_mentioned", "evidence_mentioned",
                                          "evidence_to_collect", "red_flags")}
        brief["llm_intake"] = case.get("llm")
        brief["story"] = case["story"]
        sys = ANSWER_SYS.format(language=case["language"])
        user = ANSWER_USER.format(case=json.dumps(brief, ensure_ascii=False, indent=1), facts=facts)
        attempts, removed_all = [], []
        text = self._text(sys, user, "answer")
        allowed, pairs = kb.allowed_cites(items), kb.cite_pairs(items)
        clean, removed = check(text, allowed, pairs)
        attempts.append({"raw": text, "removed": removed})
        if removed:
            text = self._text(sys, user + "\n\n" + RETRY_NOTE.format(refs=[r["text"] for r in removed]), "answer-retry")
            clean, removed = check(text, allowed, pairs)
            attempts.append({"raw": text, "removed": removed})
        given = {e["id"] for e in items}          # a real KB id from ANOTHER issue is still not allowed
        tags = re.findall(r"\[([A-Z]+-[A-Z]+)\]", clean)
        removed_all = removed + [{"kind": "kb_tag_not_given", "text": t} for t in tags if t not in given]
        used = [i for i in dict.fromkeys(tags) if i in given]
        clean = re.sub(r"\[([A-Z]+-[A-Z]+)\]", lambda m: m.group(0) if m.group(1) in given else "", clean)
        flags = "".join(f"\n> ⚠️ {f['message']}" for f in case["red_flags"])
        lang = "hi" if case["language"] == "hi" else "en"
        clean += "\n\n" + "\n".join(engine.lawyer_block(lang))     # always present, written by code
        if "LA-NALSA" not in used:
            used.append("LA-NALSA")
        src = "\n".join(f"- [{i}] " + " · ".join(kb.by_id(i)["sources"]) for i in used)
        md = f"{flags}\n\n{clean}\n\n**Draft letter (edit before sending):**\n```\n{self.draft(case)}\n```\n\n" \
             f"**Sources (checked {kb.verified_on()}):**\n{src}"
        return {"markdown": md.strip(), "kb_used": used, "guard_removed": removed_all, "attempts": attempts}

    def draft(self, case: dict) -> str:
        template = engine.draft(case)
        try:
            data = self.llm.chat_json(DRAFT_SYS, f"Story: {case['story']}\n\nTemplate:\n{template}", tag="draft",
                                      mock_fn=lambda u: {"letter": template})
            letter = str(data.get("letter") or template)
        except Exception:
            letter = template
        items = kb.entries(case["issue"])
        clean, _ = check(letter, kb.allowed_cites(items), kb.cite_pairs(items))
        return clean

    def roleplay(self, case: dict, side: str, history: list[dict]) -> str:
        sys = ROLE_SYS.format(side=side, summary=(case.get("llm") or {}).get("summary") or case["story"][:400])
        convo = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in history[-10:])
        data = self.llm.chat_json(sys + "\nReply as JSON {\"reply\": \"...\"}.", convo, tag="roleplay",
                                  mock_fn=lambda u: {"reply": "I am busy, I will see. COACH: Ask for a date."})
        clean, _ = check(str(data.get("reply", "")), [], [])
        return clean

    def _text(self, sys: str, user: str, tag: str) -> str:
        data = self.llm.chat_json(sys + "\nReturn JSON {\"answer\": \"markdown text\"}.", user, tag=tag,
                                  mock_fn=lambda u: {"answer": "Mock answer citing Section 420 IPC and [CP-LIMIT]."})
        return str(data.get("answer", ""))
