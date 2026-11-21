"""Nyaya Saathi — streamlit run app.py"""
import os

import streamlit as st

try:  # on Streamlit Cloud the key lives in the app's Secrets, not in a file
    for _k in ("GROQ_API_KEY", "GEMINI_API_KEY"):
        if _k in st.secrets and not os.environ.get(_k):
            os.environ[_k] = st.secrets[_k]
except Exception:
    pass

from lawyer import engine
from lawyer.llm import LLM, PROVIDERS, transcribe

st.set_page_config(page_title="Nyaya Saathi", page_icon="⚖️")
st.title("⚖️ Nyaya Saathi")
st.caption("Free help for three everyday problems in India: a deposit your landlord won't return, "
           "a refund that never came, and unpaid salary. General information, not legal advice. "
           "Free legal aid: call 15100. Emergency: 112.")

with st.sidebar:
    mode = st.radio("Engine", ["offline (no key)", "LLM"], help="Offline cannot invent law but understands less.")
    provider = st.selectbox("Provider", list(PROVIDERS), index=list(PROVIDERS).index("groq"), disabled=mode.startswith("offline"))
    key = st.text_input("API key (blank = use keys.env / app secrets)", type="password", disabled=mode.startswith("offline"))
    key = key or os.environ.get(PROVIDERS[provider][1] or "_none_", "")
    groq_key = os.environ.get("GROQ_API_KEY", "")
    task = st.radio("What do you want?", ["Understand my case", "Practise talking to the other side"])

if "msgs" not in st.session_state:
    st.session_state.update(msgs=[], case=None, role_hist=[])

bot = None
if mode == "LLM" and (key or provider == "ollama"):
    from lawyer.llm_engine import Lawyer
    bot = Lawyer(LLM(provider, api_key=key or None, cache_dir=".cache"))

for m in st.session_state.msgs:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

said = st.chat_input("Tell me what happened, in any language / अपनी बात किसी भी भाषा में लिखें")
audio = st.audio_input("…or speak") if hasattr(st, "audio_input") else None
if audio is not None and groq_key and not said:
    try:
        said = transcribe(audio.getvalue(), "voice.wav", "groq", groq_key)
        st.info(f"Heard: {said}")
    except Exception as e:
        st.error(f"Voice failed: {e}")

if said:
    st.session_state.msgs.append({"role": "user", "content": said})
    with st.chat_message("user"):
        st.markdown(said)
    with st.chat_message("assistant"):
        try:
            if task.startswith("Practise") and st.session_state.case and bot:
                side = {"deposit": "landlord", "consumer_refund": "customer care agent",
                        "unpaid_salary": "HR manager"}.get(st.session_state.case["issue"], "other side")
                st.session_state.role_hist.append({"role": "user", "content": said})
                reply = bot.roleplay(st.session_state.case, side, st.session_state.role_hist)
                st.session_state.role_hist.append({"role": side, "content": reply})
            else:
                story = "\n".join(m["content"] for m in st.session_state.msgs if m["role"] == "user")
                case = bot.intake(story) if bot else engine.build_case(story)
                st.session_state.case = case
                res = bot.answer(case) if bot else engine.respond(case)
                reply = res["markdown"]
                if res["guard_removed"]:
                    reply += f"\n\n_{len(res['guard_removed'])} unverified legal reference(s) were removed._"
            if task.startswith("Practise") and not bot:
                reply = "Practice mode needs the LLM engine. Here is your case analysis instead:\n\n" + reply
        except Exception as e:
            reply = f"Sorry, something went wrong: {e}"
        st.markdown(reply)
        st.session_state.msgs.append({"role": "assistant", "content": reply})

if st.session_state.msgs and st.button("Start over"):
    st.session_state.update(msgs=[], case=None, role_hist=[])
    st.rerun()
