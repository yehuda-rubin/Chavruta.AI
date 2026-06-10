# -*- coding: utf-8 -*-
"""Chavruta.AI — chat UI (task T028, Principle VII).

RTL/LTR-aware chat over the grounded pipeline: cited answers with clickable deep-links,
in-session conversation context (per spec clarification — no cross-session persistence),
honest "no source" states, responsive streaming.

    streamlit run app/streamlit_app.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import streamlit as st  # noqa: E402

from chavruta.config.profile import Profile  # noqa: E402
from chavruta.corpus.schema import Intent, Query, Turn  # noqa: E402

st.set_page_config(page_title="Chavruta.AI", page_icon="🕍", layout="centered")

st.markdown("""
<style>
  .he { direction: rtl; text-align: right; font-size: 1.05rem; }
  .en { direction: ltr; text-align: left; }
  .source-box { border-inline-start: 3px solid #888; padding: 0.4rem 0.8rem;
                margin: 0.3rem 0; background: rgba(128,128,128,0.08); border-radius: 6px; }
</style>
""", unsafe_allow_html=True)


def _is_hebrew(text: str) -> bool:
    he = sum(1 for ch in text if "א" <= ch <= "ת")
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    return he >= latin


@st.cache_resource(show_spinner="טוען את החברותא… / Loading the chavruta…")
def get_pipeline():
    from chavruta.pipeline.pipeline import ChavrutaPipeline

    return ChavrutaPipeline(Profile.from_env())


def render_message(role: str, text: str, citations=None, caveats=None) -> None:
    css = "he" if _is_hebrew(text) else "en"
    with st.chat_message("user" if role == "user" else "assistant"):
        st.markdown(f'<div class="{css}">{text}</div>', unsafe_allow_html=True)
        for caveat in (caveats or []):
            st.warning(caveat)
        if citations:
            with st.expander("📖 מקורות / Sources", expanded=False):
                for c in citations:
                    who = f" · {c.commentator_id}" if c.commentator_id else ""
                    st.markdown(
                        f'<div class="source-box he">'
                        f'<a href="{c.deep_link}" target="_blank"><b>{c.ref}</b></a>{who}<br>'
                        f'{c.quote}</div>',
                        unsafe_allow_html=True,
                    )


# ── header ──
profile = Profile.from_env()
st.title("🕍 Chavruta.AI")
st.caption(
    f"חברותא מעוגנת במקורות — כל תשובה מצוטטת | profile: **{profile.name}** · "
    f"model: `{profile.llm_model}`"
)

# ── in-session history (no cross-session persistence by design) ──
if "messages" not in st.session_state:
    st.session_state.messages = []   # [{role, text, citations, caveats}]

for m in st.session_state.messages:
    render_message(m["role"], m["text"], m.get("citations"), m.get("caveats"))

# ── input ──
question = st.chat_input("שאל שאלה בתורה… / Ask a Torah question…")
if question:
    st.session_state.messages.append({"role": "user", "text": question})
    render_message("user", question)

    pipeline = get_pipeline()
    history = [
        Turn(role=("user" if m["role"] == "user" else "assistant"), text=m["text"])
        for m in st.session_state.messages[:-1]
    ][-8:]   # bounded in-session context

    with st.spinner("מאחזר מקורות… / Retrieving sources…"):
        answer = pipeline.ask(
            Query(text=question, lang="", intent=Intent.QA), history=history
        )

    st.session_state.messages.append({
        "role": "assistant", "text": answer.text,
        "citations": answer.citations, "caveats": answer.caveats,
    })
    render_message("assistant", answer.text, answer.citations, answer.caveats)

    if answer.no_source and not answer.citations:
        st.info("לא נמצא מקור מעוגן — לא הומצאה תשובה. / No grounded source — nothing invented.")
