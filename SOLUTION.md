# Nyaya Saathi — an AI lawyer that cannot invent law (Problem 2)

## What it covers, and why these three
Three everyday problems where money is stuck and a person can act without a lawyer:
**a security deposit the landlord won't return, an online refund that never came, and unpaid salary.**
They are common, the amounts are small enough that hiring a lawyer feels pointless, and each has a
clear self-help path (written demand → free government channel → small forum). Everything else
(criminal, family, property, government employers, court notices, very large claims) is routed to a
real lawyer or free legal aid (NALSA 15100), and to 112 if someone is in danger.

## How it works
| Step | Done by | What |
| --- | --- | --- |
| Intake | LLM (offline: rules) | Messy story in English / Hindi / Hinglish / voice → case file: timeline, amount, other party, proof they have, proof to collect, 3 questions |
| Triage | **Code only** | Red flags (danger, police/crime, court notice, family, government, property, >₹50 lakh, time limits) decide "you need a lawyer". A model cannot override them |
| Where you stand | LLM, KB-only | Explains using only the verified facts for that issue, each tagged `[ID]` |
| Guard | **Code only** | Removes any Act / section / article / rule / judgment / IPC / BNS not backed by the KB (act+section pairs). One retry, then cut |
| Draft | Code template + LLM fills facts | Demand letter to landlord / grievance officer / HR |
| Practise | LLM | Plays the landlord, customer care or HR so the person can rehearse, with a coach tip |
| Lawyer block | **Code only** | "When you need a real lawyer" + free legal aid, always appended |

**How it avoids invented law.** (1) A 15-entry knowledge base (`kb/laws.json`), each fact checked against
official or reputable sources on 21 Nov 2026 with links and a caution where sources were secondary.
(2) The model only sees the KB entries for that issue and must tag them. Tags for entries it was not given
are stripped. (3) The guard scans every outgoing message. In tests it removed IPC 420, BNS 318, "Section 2(47)",
a made-up case citation, the Contract Act and "Section 12 of the Consumer Protection Act" (Section 12 is only
valid with the Legal Services Authorities Act), while keeping verified ones like Section 69 CPA and Section 45
of the Code on Wages. (4) An offline mode with no model at all.

**Examples of what it knows.** The Code on Wages, 2019 replaced the Payment of Wages Act from 21 Nov 2025.
Monthly wages are due by the 7th of the next month, and within two working days after resignation. Wage claims
can be filed within 3 years. Consumer cases up to ₹50 lakh go to the District Commission, with no fee up to
₹5 lakh, a 2-year limit, filed on e-Jagriti. E-commerce grievance officers must acknowledge within 48 hours and
resolve within a month. The Model Tenancy Act caps deposits at 2 months' rent, but only in states that adopted it.

## Test cases and results (raw outputs in `outputs/`)
14 cases (`tests/cases.json`): English, Hindi and Hinglish stories, a threat, a time-barred refund, a ₹65 lakh
claim, a government teacher, divorce, a court notice, a vague "someone owes me money", and the bait "which IPC
section can send my landlord to jail". There are also 7 adversarial guard cases of fake model outputs.
**Offline: 14/14 cases and 7/7 guard tests pass, after fixing two real bugs the tests found:**
"he *will* adjust it" fired the inheritance (*will*) flag, and "government school" was missing from the
government pattern.

**Where it still fails.**
- Hinglish amounts without a unit ("25000 deposit") are not picked up.
- Keyword evidence detection overclaims: the word "ऑर्डर" is taken to mean the person has an order ID.
- It over-refuses: the IPC bait gets only a lawyer referral, not the civil deposit route it could still use.
- Drafts are English only.
- State rent laws are not covered.
- The KB goes stale: it carries a `verified_on` date and needs a lawyer review each quarter.
- The LLM mode was tested only with a mock model here. Run `python run_tests.py --backend llm` with a real key.

## Scale and cost
About 3–4 model calls per conversation (intake, answer, maybe a retry, draft), roughly 6–8k tokens. That is well
under ₹1 on a Flash-class model. The offline mode is free. Adding a new problem means adding lawyer-reviewed KB
entries, keywords and a template. The guard and triage do not change. A real deployment would add a
lawyer-review queue for new KB entries and log every guard removal as a signal of where the model hallucinates.
