# Nyaya Saathi — AI legal helper for everyday problems in India

Covers: **security deposit not returned · online refund not received · unpaid salary.**
Everything else is referred to a lawyer / free legal aid (NALSA 15100). Read `SOLUTION.md` for the design.

## API key (Groq) — one-time setup
1. Get a free key: https://console.groq.com/keys
2. Open **`keys.env`** in this folder (`open -e keys.env` on Mac) and paste it after `GROQ_API_KEY=`, save.
3. That is it: every command below reads it. `keys.env` is in `.gitignore`, so it never goes to GitHub.
4. On Streamlit Cloud: App → Settings → **Secrets**, add the line `GROQ_API_KEY = "your_key"`.

If Groq says "model not found", change `LLM_MODEL=` in `keys.env` to a model from https://console.groq.com/docs/models.

```bash
pip install -r requirements.txt
python run_tests.py                                   # offline, no key: 14 cases + 7 guard tests
python run_tests.py --backend llm                     # same cases through Groq (key from keys.env)
streamlit run app.py                                  # chat UI; voice also uses the Groq key
```

| file | what |
| --- | --- |
| `kb/laws.json` | the only source of legal statements; each with sources and `verified_on` |
| `lawyer/triage.py` | issue detection + red flags (code decides when a lawyer is needed) |
| `lawyer/guard.py` | removes any legal reference the KB does not back |
| `lawyer/engine.py` | offline engine: case file, options, drafts |
| `lawyer/llm_engine.py` | LLM intake, KB-only answers, drafts, role-play |
| `lawyer/llm.py` | OpenAI-compatible client (Gemini, Groq, OpenRouter, Ollama…) + Whisper transcription |
| `tests/` | test cases and adversarial guard cases |

General information, not legal advice.
