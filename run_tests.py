"""Run every test case and save raw, unedited outputs.

python run_tests.py                                  # offline engine, no key
python run_tests.py --backend llm --provider gemini  # LLM engine (GEMINI_API_KEY)
"""
import argparse
import json
from pathlib import Path

from lawyer import engine, guard, kb

HERE = Path(__file__).parent


def run_guard_tests():
    rows = []
    for g in json.loads((HERE / "tests/guard_cases.json").read_text()):
        items = kb.entries(g["issue"])
        clean, removed = guard.check(g["text"], kb.allowed_cites(items), kb.cite_pairs(items))
        rem = " | ".join(r["text"] for r in removed)
        ok = all(m in rem for m in g["must_remove"]) and all(k in clean for k in g["must_keep"])
        rows.append({"id": g["id"], "pass": ok, "input": g["text"], "output": clean, "removed": removed})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["offline", "llm"], default="offline")
    ap.add_argument("--provider", default=None, help="default: groq (keys.env)")
    ap.add_argument("--model")
    ap.add_argument("--api-key")
    ap.add_argument("--out")
    a = ap.parse_args()
    from lawyer.llm import DEFAULT_PROVIDER
    out = Path(a.out or f"outputs/{a.backend if a.backend == 'offline' else (a.provider or DEFAULT_PROVIDER)}")
    out.mkdir(parents=True, exist_ok=True)
    bot = None
    if a.backend == "llm":
        from lawyer.llm import LLM
        from lawyer.llm_engine import Lawyer
        bot = Lawyer(LLM(a.provider, a.model, a.api_key, cache_dir=out / ".cache", log_path=out / "llm_raw_log.jsonl"))
    summary = []
    for c in json.loads((HERE / "tests/cases.json").read_text()):
        case = bot.intake(c["text"]) if bot else engine.build_case(c["text"])
        res = bot.answer(case) if bot else engine.respond(case)
        exp = c["expect"]
        codes = [f["code"] for f in case["red_flags"]]
        checks = {
            "issue": exp.get("issue") in (None, case["issue"]),
            "in_scope": exp.get("in_scope") in (None, case["in_scope"]),
            "flags": all(f in codes for f in exp.get("flags", [])),
            "no_unverified_law_left": not guard.check(res["markdown"], kb.allowed_cites(kb.entries()),
                                                      kb.cite_pairs(kb.entries()))[1],
            "says_when_to_get_lawyer": any(w in res["markdown"].lower() for w in
                                          ["lawyer", "वकील", "15100", "legal aid"]),
        }
        summary.append({"id": c["id"], "pass": all(checks.values()), "checks": checks, "issue": case["issue"],
                        "language": case["language"], "in_scope": case["in_scope"], "red_flags": codes,
                        "kb_used": res["kb_used"], "guard_removed": res["guard_removed"]})
        (out / f"{c['id']}.md").write_text(f"## Input\n\n{c['text']}\n\n## Output\n\n{res['markdown']}\n", encoding="utf-8")
        (out / f"{c['id']}.json").write_text(json.dumps({"case": case, "result": res}, indent=2, ensure_ascii=False),
                                             encoding="utf-8")
    g = run_guard_tests()
    (out / "guard_tests.json").write_text(json.dumps(g, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    for s in summary:
        bad = [k for k, v in s["checks"].items() if not v]
        print(f"{'PASS' if s['pass'] else 'FAIL'}  {s['id']:<26} issue={s['issue']:<16} lang={s['language']:<8} "
              f"in_scope={s['in_scope']!s:<5} flags={s['red_flags']} {'' if not bad else 'failed: ' + str(bad)}")
    print(f"\nCases: {sum(s['pass'] for s in summary)}/{len(summary)} pass · "
          f"Guard tests: {sum(x['pass'] for x in g)}/{len(g)} pass · outputs in {out}/")


if __name__ == "__main__":
    main()
