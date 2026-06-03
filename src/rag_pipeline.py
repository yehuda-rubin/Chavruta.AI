"""
src/rag_pipeline.py — Chavruta.AI
===================================
צינור RAG מקומי מלא:
  שאלה → הטמעה → ChromaDB → Prompt → Ollama → תשובה + מקורות

שימוש:
  from src.rag_pipeline import ChavrутаPipeline

  pipeline = ChavrutaPipeline()
  answer = pipeline.ask("מה אומר רש\"י על בריאת האור?")
  print(answer["response"])
  print(answer["sources"])

  # מצב שיחה (multi-turn):
  for chunk in pipeline.stream("מה ההבדל בין רש\"י לרמב\"ן בפרשת בראשית?"):
      print(chunk, end="", flush=True)

הרצה ישירה (CLI):
  python src/rag_pipeline.py
  python src/rag_pipeline.py --query "מה אומר רש\"י על בריאת האור?"
"""

from __future__ import annotations

import json
import sys
import argparse
import logging
from pathlib import Path
from typing import Iterator

# ─── נתיבים ──────────────────────────────────────────────────────────────────
ROOT_DIR       = Path(__file__).resolve().parent.parent
CHROMA_DB_PATH = ROOT_DIR / "data" / "chroma_db"

# ─── הגדרות ──────────────────────────────────────────────────────────────────
EMBEDDING_MODEL  = "BAAI/bge-m3"   # רב-לשוני (עברית+אנגלית), 1024 מימד
COLLECTION_NAME  = "chavruta_torah"
OLLAMA_BASE_URL  = "http://127.0.0.1:11434"
OLLAMA_MODEL     = "granite4.1:3b"     # ollama pull granite4.1:3b (לא-thinking)
TOP_K            = 3                   # צ'אנקים לשליפה
MAX_CONTEXT_CHARS = 7000               # מגבלת הקשר (Granite 4 — קונטקסט ארוך; מקור מלא לציטוט)

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════════
# Prompt Templates
# ════════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are Chavruta, a traditional and learned Torah study partner.
Answer Torah questions based ONLY on the provided sources (Chumash, Rashi, Ramban, and other commentators).

Rules:
• Respond in the SAME language as the user's question. Hebrew question → answer in Hebrew; English question → answer in English.
• Quote the relevant Hebrew source text verbatim, then explain it.
• Rely ONLY on the provided sources — never invent or add outside information.
• Cite the source (book, chapter, verse, commentator) for every claim.
• When Rashi and Ramban disagree, present both views.
• If the sources do not cover the question, say so honestly.
• Keep a respectful, clear, scholarly tone. Answer directly — do NOT show reasoning or <think> tags."""

CONTEXT_TEMPLATE = """--- SOURCES ---
{context_blocks}
--- END SOURCES ---"""

QUERY_TEMPLATE = """Question: {query}"""

# מיפוי שם ספר (תעתיק) → ref של Sefaria (להעשרה חיה, שלב 1)
BOOK_TO_SEFARIA = {
    "Bereishit": "Genesis", "Shemot": "Exodus", "Vayikra": "Leviticus",
    "Bamidbar": "Numbers", "Devarim": "Deuteronomy",
}

# שם מפרש קנוני → כינויים (עברית + אנגלית) לזיהוי בשאלה
COMMENTATORS_CANON = {
    "Rashi":          ["rashi", 'רש"י', "רשי"],
    "Ramban":         ["ramban", "nachmanides", 'רמב"ן', "רמבן"],
    "Ibn Ezra":       ["ibn ezra", "אבן עזרא", 'ראב"ע'],
    "Radak":          ["radak", "kimchi", 'רד"ק', "רדק"],
    "Sforno":         ["sforno", "ספורנו"],
    "Rashbam":        ["rashbam", 'רשב"ם', "רשבם"],
    "Or HaChaim":     ["or hachaim", "ohr hachaim", "אור החיים", 'אוה"ח'],
    "Malbim":         ["malbim", 'מלבי"ם', "מלבים"],
    "Metzudat David": ["metzudat david", "מצודת דוד", "מצודות"],
    "Metzudat Zion":  ["metzudat zion", "מצודת ציון"],
    "Onkelos":        ["onkelos", "אונקלוס", "targum onkelos", "תרגום אונקלוס"],
    "Targum Jonathan":["targum jonathan", "תרגום יונתן", "יונתן בן עוזיאל"],
}


# ════════════════════════════════════════════════════════════════════════════════
# Pipeline
# ════════════════════════════════════════════════════════════════════════════════

class ChavrutaPipeline:
    """
    צינור RAG מלא לחברותא.

    Parameters
    ----------
    top_k : int
        כמה צ'אנקים לשלוף מ-ChromaDB (ברירת מחדל: 6)
    ollama_model : str
        שם המודל ב-Ollama (ברירת מחדל: "llama3.1")
    verbose : bool
        הדפסת מידע debug
    """

    def __init__(
        self,
        top_k: int = TOP_K,
        ollama_model: str = OLLAMA_MODEL,
        verbose: bool = False,
    ) -> None:
        self.top_k        = top_k
        self.ollama_model = ollama_model

        if verbose:
            logging.getLogger().setLevel(logging.INFO)

        self._model      = None   # lazy-loaded
        self._store      = None   # lazy-loaded

    # ── Lazy loading ──────────────────────────────────────────────────────────

    @property
    def model(self):
        if self._model is None:
            log.info("טוען מודל embedding: %s", EMBEDDING_MODEL)
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
            self._model.max_seq_length = 512   # תואם לבנייה (bge-m3)
            log.info("מודל נטען.")
        return self._model

    @property
    def store(self):
        if self._store is None:
            try:
                from vector_store import get_store      # הרצה כסקריפט מתוך src/
            except ImportError:
                from .vector_store import get_store      # ייבוא כחבילה
            self._store = get_store()
            log.info("Vector store: %s | וקטורים: %d", self._store.mode, self._store.count())
        return self._store

    # ── Retrieval ─────────────────────────────────────────────────────────────

    @staticmethod
    def _detect_intent(query: str) -> str:
        """
        מזהה את כוונת השאלה ומחזיר מצב שליפה:
          'rashi'      → שאלה על רש"י בלבד
          'ramban'     → שאלה על רמב"ן בלבד
          'comparison' → השוואה בין רש"י לרמב"ן
          'chumash'    → שאלה על הטקסט/פסוק עצמו
          'general'    → mix לפי similarity
        """
        q = query.lower()

        wants_rashi  = any(w in q for w in ["rashi", 'רש"י', "רשי", "rashi's"])
        wants_ramban = any(w in q for w in ["ramban", 'רמב"ן', "רמבן", "nachmanides", "nachman"])
        wants_cmp    = any(w in q for w in [
            "difference", "compare", "comparison", "vs", "versus",
            'הבדל', "לעומת", "בניגוד", "שניהם", "both",
        ])
        wants_text   = any(w in q for w in [
            "verse", "text", "written", "says in torah", "torah says",
            "כתוב", "פסוק", "התורה אומרת",
        ])

        if wants_cmp or (wants_rashi and wants_ramban):
            return "comparison"
        if wants_rashi:
            return "rashi"
        if wants_ramban:
            return "ramban"
        if wants_text:
            return "chumash"
        return "general"

    @staticmethod
    def _detect_commentators(query: str) -> list[str]:
        """מזהה אילו מפרשים מוזכרים בשאלה (לפי כינויים עבריים/אנגליים)."""
        q = query.lower()
        found = []
        for name, aliases in COMMENTATORS_CANON.items():
            if any(a.lower() in q for a in aliases):
                found.append(name)
        return found

    def _query_by_type(self, vec: list, chunk_type: str, k: int) -> list[dict]:
        """שולף k צ'אנקים מסוג מסוים (דרך שכבת ה-store)."""
        return self.store.search(vec, k, chunk_type=chunk_type)

    def retrieve(self, query: str, k: int | None = None, enrich: bool = False) -> list[dict]:
        """
        שולף צ'אנקים לפי כוונת השאלה (smart retrieval).

        מצבים:
          comparison → 1 חומש + 1 רש"י + 1 רמב"ן
          rashi      → 2 רש"י  + 1 חומש
          ramban     → 2 רמב"ן + 1 חומש
          chumash    → 3 חומש
          general    → top-3 לפי similarity (ללא סינון)
        """
        k     = k or self.top_k
        vec   = self.model.encode([query], normalize_embeddings=True)[0].tolist()
        named = self._detect_commentators(query)
        log.info("מפרשים בשאלה: %s", named or "—")

        # עוגן ראשי (primary): הפסוקים הרלוונטיים ביותר
        chunks = self.store.search(vec, 2, chunk_type="pasuk")

        if named:
            # שאלה על מפרש/ים ספציפיים → הבא אותם
            per = max(2, k // len(named))
            for name in named:
                chunks += self.store.search(vec, per, commentator=name)
        else:
            # כללי → מיטב הפירושים לפי דמיון (כל מפרש)
            chunks += self.store.search(vec, k, chunk_type="commentary")

        # dedup לפי (פסוק, מפרש) + מיון לפי דמיון
        seen, uniq = set(), []
        for c in chunks:
            key = (c["meta"].get("verse_id"), c["meta"].get("commentator"))
            if key in seen:
                continue
            seen.add(key)
            uniq.append(c)
        uniq.sort(key=lambda x: x["similarity"], reverse=True)

        # שלב 1 — העשרה חיה מ-Sefaria (אופציונלי, מקוון)
        if enrich:
            uniq = uniq + self.enrich_with_sefaria(uniq)
        return uniq

    def enrich_with_sefaria(self, chunks: list[dict],
                            names: list[str] | None = None) -> list[dict]:
        """
        מעשיר את ההקשר במפרשים נוספים מ-Sefaria על הפסוק המרכזי (התוצאה העליונה):
        אבן-עזרא, רד"ק, ספורנו, רשב"ם, אור החיים — מעבר לרש"י/רמב"ן המקומיים.
        דורש אינטרנט (הפרופיל המקוון). מחזיר צ'אנקים בפורמט הרגיל.
        """
        if not chunks:
            return []
        m = chunks[0]["meta"]
        book, ch, vs = m.get("book", ""), m.get("chapter"), m.get("verse")
        sef_book = BOOK_TO_SEFARIA.get(book)
        if not (sef_book and ch and vs):
            return []
        ref = f"{sef_book} {ch}:{vs}"

        try:
            import sefaria_client
        except ImportError:
            from . import sefaria_client

        extra = names or ["Ibn Ezra", "Radak", "Sforno", "Rashbam", "Or HaChaim"]
        have = {c["meta"].get("commentator", "") for c in chunks}
        anchor_sim = chunks[0].get("similarity", 0.5)

        try:
            fetched = sefaria_client.get_commentaries(ref, names=extra, include_targum=False)
        except Exception as e:
            log.warning("Sefaria enrich נכשל (%s) — ממשיך בלי העשרה", e)
            return []

        out = []
        for c in fetched:
            if c["commentator"] in have or not (c["he"] or c["en"]):
                continue
            doc = f"[{c['commentator']}] {book} {ch}:{vs}\n{c['he']}\n{c['en']}"
            out.append({
                "meta": {"book": book, "chapter": ch, "verse": vs,
                         "chunk_type": "commentary", "commentator": c["commentator"],
                         "verse_id": m.get("verse_id", "")},
                "document":   doc,
                "similarity": round(anchor_sim - 0.01, 4),
                "distance":   round(1 - (anchor_sim - 0.01), 4),
            })
        log.info("Sefaria enrich: +%d מפרשים על %s", len(out), ref)
        return out

    # ── Prompt Builder ────────────────────────────────────────────────────────

    def _format_chunk(self, chunk: dict) -> str:
        """ממיר צ'אנק לבלוק טקסט לפרומפט."""
        meta = chunk["meta"]
        book = meta.get("book", "?")
        ch   = meta.get("chapter", "?")
        vs   = meta.get("verse", "?")
        ct   = meta.get("chunk_type", "?")
        cmt  = meta.get("commentator", "")

        # כותרת
        if ct in ("pasuk", "chumash"):
            header = f"[{book} {ch}:{vs}]"
        elif cmt:
            header = f"[{cmt}] {book} {ch}:{vs}"
        else:
            header = f"[{ct}] {book} {ch}:{vs}"

        # גוף — מלוא טקסט המקור (חיתוך רק אם ארוך מאוד) כדי שהמודל יצטט נכון
        lines = chunk["document"].split("\n")
        body = "\n".join(l for l in lines[1:] if l.strip())
        if len(body) > 1500:
            body = body[:1500].rsplit(" ", 1)[0] + "..."

        return f"{header}\n{body}"

    @staticmethod
    def _answer_language_hint(query: str) -> str:
        """הנחיית שפת תשובה לפי שפת השאלה (עברית אם יש אותיות עבריות)."""
        has_he = any("֐" <= c <= "ת" for c in query)
        return "ענה בעברית בלבד." if has_he else "Answer in English only."

    def build_prompt(
        self,
        query: str,
        chunks: list[dict],
        history: list[dict] | None = None,
    ) -> list[dict]:
        """
        בונה את הפרומפט לOllama בפורמט messages.

        Parameters
        ----------
        query   : שאלת המשתמש
        chunks  : תוצאות ה-retrieval
        history : היסטוריית שיחה [(role, content), ...]
        """
        # הרכבת בלוקי הקשר
        context_parts = []
        total_chars   = 0

        for chunk in chunks:
            block = self._format_chunk(chunk)
            if total_chars + len(block) > MAX_CONTEXT_CHARS:
                break
            context_parts.append(block)
            total_chars += len(block)

        context = CONTEXT_TEMPLATE.format(
            context_blocks="\n\n".join(context_parts)
        )

        # הרכבת messages
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        # היסטוריה (אם קיימת)
        if history:
            messages.extend(history)

        # שאלה + הקשר + הנחיית שפה מפורשת (אמינה יותר מ-system לבדו)
        hint = self._answer_language_hint(query)
        user_content = f"{context}\n\n{QUERY_TEMPLATE.format(query=query)}\n\n{hint}"
        messages.append({"role": "user", "content": user_content})

        return messages

    # ── Ollama ────────────────────────────────────────────────────────────────

    def _call_ollama(
        self,
        messages: list[dict],
        stream: bool = False,
    ) -> str | Iterator[str]:
        """שולח בקשה ל-Ollama API באמצעות ספריית ollama."""
        try:
            import ollama as ollama_lib
        except ImportError:
            raise RuntimeError("ספריית ollama לא מותקנת. הרץ: pip install ollama")

        try:
            if stream:
                return self._stream_ollama(messages)
            else:
                response = ollama_lib.chat(
                    model=self.ollama_model,
                    messages=messages,
                    options={
                        "temperature": 0.3,
                        "num_ctx":     8192,
                    },
                )
                return response["message"]["content"]
        except Exception as e:
            raise RuntimeError(
                f"שגיאת Ollama: {e}\n"
                f"ודא ש-Ollama רץ: ollama serve\n"
                f"ומודל קיים: ollama pull {self.ollama_model}"
            ) from e

    def _stream_ollama(self, messages: list[dict]) -> Iterator[str]:
        """גנרטור streaming באמצעות ספריית ollama."""
        import ollama as ollama_lib
        stream = ollama_lib.chat(
            model=self.ollama_model,
            messages=messages,
            stream=True,
            options={
                "temperature": 0.3,
                "num_ctx":     8192,
            },
        )
        for chunk in stream:
            token = chunk.get("message", {}).get("content", "")
            if token:
                yield token

    # ── Public API ────────────────────────────────────────────────────────────

    def ask(
        self,
        query: str,
        history: list[dict] | None = None,
        enrich: bool = False,
    ) -> dict:
        """
        שאלה מלאה — retrieval + generation.

        Returns
        -------
        dict:
            response  : str  — תשובת המודל
            sources   : list — מקורות ששימשו
            chunks    : list — הצ'אנקים המלאים
        """
        log.info("שאלה: %s", query)

        # 1. Retrieval
        chunks = self.retrieve(query, enrich=enrich)
        log.info("נשלפו %d צ'אנקים", len(chunks))

        # 2. Prompt
        messages = self.build_prompt(query, chunks, history)

        # 3. Inference
        response = self._call_ollama(messages, stream=False)

        # 4. עיצוב מקורות
        sources = self._format_sources(chunks)

        return {
            "query":    query,
            "response": response,
            "sources":  sources,
            "chunks":   chunks,
        }

    def stream(
        self,
        query: str,
        history: list[dict] | None = None,
    ) -> Iterator[str]:
        """
        מצב streaming — מחזיר tokens בזרם.

        שימוש:
            for token in pipeline.stream("שאלה"):
                print(token, end="", flush=True)
        """
        chunks   = self.retrieve(query)
        messages = self.build_prompt(query, chunks, history)
        yield from self._call_ollama(messages, stream=True)

    @staticmethod
    def _format_sources(chunks: list[dict]) -> list[str]:
        """מחזיר רשימת ציטוטי מקורות."""
        seen    = set()
        sources = []

        for chunk in chunks:
            meta = chunk["meta"]
            book = meta.get("book", "?")
            ch   = meta.get("chapter", "?")
            vs   = meta.get("verse", "?")
            ct   = meta.get("chunk_type", "?")
            cmt  = meta.get("commentator", "")

            if ct in ("pasuk", "chumash"):
                label = f"{book} {ch}:{vs}"
            elif cmt:
                label = f"{cmt} — {book} {ch}:{vs}"
            else:
                label = f"{ct} — {book} {ch}:{vs}"

            if label not in seen:
                seen.add(label)
                sources.append(f"📖 {label}  (sim={chunk['similarity']:.3f})")

        return sources


# ════════════════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════════════════

def interactive_chat(pipeline: ChavrutaPipeline) -> None:
    """לולאת שיחה אינטראקטיבית."""
    print("\n" + "═" * 60)
    print("  🕍  Chavruta.AI — מצב שיחה")
    print("  הקלד 'יציאה' או 'exit' לסיום")
    print("═" * 60 + "\n")

    history: list[dict] = []

    while True:
        try:
            query = input("🙋 שאלה: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nשלום!")
            break

        if not query:
            continue
        if query.lower() in ("יציאה", "exit", "quit", "q"):
            print("שלום!")
            break

        print("\n🤔 מחפש...")

        try:
            # Streaming
            print("\n📜 תשובה:\n")
            chunks_used = []

            # נשלף צ'אנקים פעם אחת
            chunks = pipeline.retrieve(query)
            messages = pipeline.build_prompt(query, chunks, history)

            full_response = ""
            for token in pipeline._call_ollama(messages, stream=True):
                print(token, end="", flush=True)
                full_response += token

            print("\n")

            # הוסף להיסטוריה
            history.append({"role": "user",      "content": query})
            history.append({"role": "assistant",  "content": full_response})

            # שמור רק 6 הודעות אחרונות (3 סיבובים)
            if len(history) > 6:
                history = history[-6:]

            # הצג מקורות
            sources = pipeline._format_sources(chunks)
            print("─" * 50)
            print("מקורות:")
            for s in sources:
                print(f"  {s}")
            print()

        except RuntimeError as e:
            print(f"\n❌ שגיאה: {e}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Chavruta.AI — RAG Pipeline")
    parser.add_argument("--query",   "-q", type=str, help="שאלה חד-פעמית")
    parser.add_argument("--top-k",   "-k", type=int, default=TOP_K,
                        help=f"כמה צ'אנקים לשלוף (ברירת מחדל: {TOP_K})")
    parser.add_argument("--model",   "-m", type=str, default=OLLAMA_MODEL,
                        help=f"מודל Ollama (ברירת מחדל: {OLLAMA_MODEL})")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    pipeline = ChavrutaPipeline(
        top_k=args.top_k,
        ollama_model=args.model,
        verbose=args.verbose,
    )

    if args.query:
        # מצב חד-פעמי
        result = pipeline.ask(args.query)
        print(f"\n📜 תשובה:\n{result['response']}\n")
        print("─" * 50)
        print("מקורות:")
        for s in result["sources"]:
            print(f"  {s}")
    else:
        # מצב שיחה
        interactive_chat(pipeline)


if __name__ == "__main__":
    main()
