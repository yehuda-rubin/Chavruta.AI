"""
app.py — Chavruta.AI Streamlit Interface
=========================================
הרצה:
  streamlit run app.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
from src.rag_pipeline import ChavrutaPipeline

# ─── Page Config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="חברותא AI",
    page_icon="🕍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── RTL + Style ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
  /* RTL global */
  .stApp { direction: rtl; }
  .stMarkdown, .stText, p, li, h1, h2, h3, label { direction: rtl; text-align: right; }

  /* Chat bubbles */
  .user-bubble {
    background: #1a3a5c;
    color: #e8f0fe;
    border-radius: 18px 18px 4px 18px;
    padding: 12px 16px;
    margin: 8px 0;
    max-width: 80%;
    margin-right: auto;
  }
  .assistant-bubble {
    background: #1e2a1e;
    color: #d4edda;
    border-radius: 18px 18px 18px 4px;
    padding: 12px 16px;
    margin: 8px 0;
    max-width: 90%;
    margin-left: auto;
  }

  /* Source cards */
  .source-card {
    background: #2a2a1e;
    border-right: 3px solid #c8a84b;
    border-radius: 4px;
    padding: 8px 12px;
    margin: 4px 0;
    font-size: 0.85em;
    color: #d4c88a;
  }

  /* Input */
  .stTextArea textarea {
    direction: rtl;
    font-size: 1.05em;
  }

  /* Sidebar */
  section[data-testid="stSidebar"] { direction: rtl; }
</style>
""", unsafe_allow_html=True)


# ─── Session State ────────────────────────────────────────────────────────────
if "pipeline" not in st.session_state:
    st.session_state.pipeline = None

if "messages" not in st.session_state:
    st.session_state.messages = []   # [{role, content, sources}]

if "loading" not in st.session_state:
    st.session_state.loading = False


# ─── Pipeline Loader ─────────────────────────────────────────────────────────
@st.cache_resource(show_spinner="טוען מודל ו-DB...")
def load_pipeline(top_k: int, model: str) -> ChavrutaPipeline:
    return ChavrutaPipeline(top_k=top_k, ollama_model=model)


# ════════════════════════════════════════════════════════════════════════════════
# Sidebar
# ════════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.title("🕍 חברותא AI")
    st.caption("עוזר לימוד תורה מקומי")
    st.divider()

    st.subheader("⚙️ הגדרות")

    top_k = st.slider(
        "מספר מקורות לשליפה",
        min_value=3, max_value=12, value=6, step=1,
        help="כמה צ'אנקים לשלוף מה-DB לכל שאלה"
    )

    ollama_model = st.selectbox(
        "מודל Ollama",
        ["granite4.1:3b", "qwen3:4b", "gemma3:4b", "mistral"],
        index=0,
    )

    st.divider()

    # כפתור טעינה
    if st.button("🔌 טען מודל", use_container_width=True, type="primary"):
        with st.spinner("טוען..."):
            st.session_state.pipeline = load_pipeline(top_k, ollama_model)
        st.success("מוכן!")

    # סטטוס
    if st.session_state.pipeline:
        col = st.session_state.pipeline.collection
        total = col.count()
        st.success(f"✅ DB פעיל — {total:,} וקטורים")
    else:
        st.warning("⚠️ המודל לא נטען")

    st.divider()

    # ניקוי שיחה
    if st.button("🗑️ נקה שיחה", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.divider()
    st.caption("Chavruta.AI • Local RAG • חמישה חומשי תורה")
    st.caption("רש\"י • רמב\"ן • בגרסא מקומית")


# ════════════════════════════════════════════════════════════════════════════════
# Main Area
# ════════════════════════════════════════════════════════════════════════════════
st.title("🕍 חברותא AI")
st.caption("שאל כל שאלה בתורה — בעברית או באנגלית")

# ── היסטוריית שיחה ────────────────────────────────────────────────────────────
chat_container = st.container()

with chat_container:
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            st.markdown(
                f'<div class="user-bubble">🙋 {msg["content"]}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="assistant-bubble">{msg["content"]}</div>',
                unsafe_allow_html=True,
            )
            # מקורות
            if msg.get("sources"):
                with st.expander(f"📖 מקורות ({len(msg['sources'])})", expanded=False):
                    for src in msg["sources"]:
                        st.markdown(
                            f'<div class="source-card">{src}</div>',
                            unsafe_allow_html=True,
                        )
            if msg.get("chunks"):
                with st.expander("📄 צ'אנקים מלאים", expanded=False):
                    for i, chunk in enumerate(msg["chunks"], 1):
                        meta = chunk["meta"]
                        book = meta.get("book", "?")
                        ch   = meta.get("chapter", "?")
                        vs   = meta.get("verse", "?")
                        ct   = meta.get("chunk_type", "?")
                        sim  = chunk["similarity"]
                        st.markdown(f"**{i}. [{ct}] {book} {ch}:{vs}** — sim={sim:.3f}")
                        st.text(chunk["document"][:400])
                        st.divider()


# ── קלט משתמש ────────────────────────────────────────────────────────────────
st.divider()

col1, col2 = st.columns([5, 1])

with col1:
    query = st.text_area(
        "שאלה:",
        placeholder='למשל: "מה אומר רש"י על בריאת האור?" או "What does Ramban say about creation?"',
        height=80,
        label_visibility="collapsed",
        key="query_input",
    )

with col2:
    submit = st.button("➤ שאל", use_container_width=True, type="primary")

# ── עיבוד שאלה ───────────────────────────────────────────────────────────────
if submit and query.strip():
    if not st.session_state.pipeline:
        st.error("❌ טען את המודל קודם (כפתור 'טען מודל' בסרגל הצד)")
    else:
        # הוסף שאלת משתמש להיסטוריה
        st.session_state.messages.append({
            "role":    "user",
            "content": query.strip(),
        })

        # הכן היסטוריה ל-pipeline (ללא sources/chunks)
        history = [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.messages[:-1]
            if m["role"] in ("user", "assistant")
        ][-6:]  # 3 סיבובים אחרונים

        pipeline = st.session_state.pipeline

        # שליפת צ'אנקים
        with st.spinner("🔍 מחפש במקורות..."):
            chunks   = pipeline.retrieve(query.strip())
            messages = pipeline.build_prompt(query.strip(), chunks, history)

        # Streaming response
        with chat_container:
            st.markdown(
                '<div class="user-bubble">🙋 ' + query.strip() + '</div>',
                unsafe_allow_html=True,
            )

            response_placeholder = st.empty()
            full_response = ""

            try:
                for token in pipeline._call_ollama(messages, stream=True):
                    full_response += token
                    response_placeholder.markdown(
                        f'<div class="assistant-bubble">{full_response}▌</div>',
                        unsafe_allow_html=True,
                    )

                # הסר cursor
                response_placeholder.markdown(
                    f'<div class="assistant-bubble">{full_response}</div>',
                    unsafe_allow_html=True,
                )

            except RuntimeError as e:
                response_placeholder.error(f"❌ {e}")
                full_response = f"שגיאה: {e}"

        # שמור ב-session
        sources = pipeline._format_sources(chunks)
        st.session_state.messages.append({
            "role":    "assistant",
            "content": full_response,
            "sources": sources,
            "chunks":  chunks,
        })

        st.rerun()

# ── מסך ריק — הוראות ─────────────────────────────────────────────────────────
if not st.session_state.messages:
    st.markdown("""
    <div style="text-align:center; padding:40px; color:#888;">
        <h2>ברוך הבא לחברותא AI 🕍</h2>
        <p>עוזר לימוד תורה מקומי — חמישה חומשי תורה עם רש"י ורמב"ן</p>
        <br>
        <b>שאלות לדוגמה:</b>
        <ul style="list-style:none; padding:0;">
            <li>🔹 מה ההבדל בין רש"י לרמב"ן על פסוק הראשון?</li>
            <li>🔹 מה טעם ציווי המילה לאברהם?</li>
            <li>🔹 Why did God create the world?</li>
            <li>🔹 מה פשר חלום יעקב?</li>
        </ul>
        <br>
        <small>← טען מודל בסרגל הצד כדי להתחיל</small>
    </div>
    """, unsafe_allow_html=True)
