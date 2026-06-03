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
EMBEDDING_MODEL  = "BAAI/bge-small-en-v1.5"
COLLECTION_NAME  = "chavruta_torah"
OLLAMA_BASE_URL  = "http://127.0.0.1:11434"
OLLAMA_MODEL     = "qwen3.5:4b"        # ollama pull qwen3.5:4b
TOP_K            = 3                   # צ'אנקים לשליפה
MAX_CONTEXT_CHARS = 2000               # מגבלת הקשר בפרומפט

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

SYSTEM_PROMPT = """אתה חברותא — עוזר לימוד תורה מסורתי ומלומד.
תפקידך לענות על שאלות בתורה על בסיס המקורות שסופקו: חומש, רש"י ורמב"ן.

כללים:
• ענה תמיד בעברית, גם אם השאלה באנגלית.
• הסתמך אך ורק על המקורות שניתנו — אל תמציא.
• ציין את המקור (ספר, פרק, פסוק, מפרש) בכל טענה.
• כשיש מחלוקת בין רש"י לרמב"ן — הצג את שתי הדעות.
• אם המקורות אינם מכסים את השאלה — אמור זאת בכנות.
• שמור על טון של לומד תורה — ענייני, מכבד, בהיר.
• אל תוסיף תגי <think> או חשיבה גלויה — ענה ישירות בלבד."""

CONTEXT_TEMPLATE = """--- מקורות ---
{context_blocks}
--- סוף מקורות ---"""

QUERY_TEMPLATE = """שאלה: {query}

תשובה:"""


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
        self._collection = None   # lazy-loaded

    # ── Lazy loading ──────────────────────────────────────────────────────────

    @property
    def model(self):
        if self._model is None:
            log.info("טוען מודל embedding: %s", EMBEDDING_MODEL)
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(EMBEDDING_MODEL, device="cpu")
            log.info("מודל נטען.")
        return self._model

    @property
    def collection(self):
        if self._collection is None:
            log.info("מתחבר ל-ChromaDB: %s", CHROMA_DB_PATH)
            import chromadb
            from chromadb.config import Settings
            client = chromadb.PersistentClient(
                path=str(CHROMA_DB_PATH),
                settings=Settings(anonymized_telemetry=False),
            )
            self._collection = client.get_collection(COLLECTION_NAME)
            log.info("חובר. סה\"כ וקטורים: %d", self._collection.count())
        return self._collection

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

    def _query_by_type(self, vec: list, chunk_type: str, k: int) -> list[dict]:
        """שולף k צ'אנקים מסוג מסוים."""
        result = self.collection.query(
            query_embeddings=vec,
            n_results=k,
            where={"chunk_type": chunk_type},
            include=["metadatas", "distances", "documents"],
        )
        return [
            {
                "meta":       meta,
                "distance":   dist,
                "similarity": round(1 - dist, 4),
                "document":   doc,
            }
            for meta, dist, doc in zip(
                result["metadatas"][0],
                result["distances"][0],
                result["documents"][0],
            )
        ]

    def retrieve(self, query: str, k: int | None = None) -> list[dict]:
        """
        שולף צ'אנקים לפי כוונת השאלה (smart retrieval).

        מצבים:
          comparison → 1 חומש + 1 רש"י + 1 רמב"ן
          rashi      → 2 רש"י  + 1 חומש
          ramban     → 2 רמב"ן + 1 חומש
          chumash    → 3 חומש
          general    → top-3 לפי similarity (ללא סינון)
        """
        k   = k or self.top_k
        vec = self.model.encode([query], normalize_embeddings=True).tolist()
        intent = self._detect_intent(query)
        log.info("intent: %s", intent)

        if intent == "comparison":
            chunks = (
                self._query_by_type(vec, "chumash", 1) +
                self._query_by_type(vec, "rashi",   1) +
                self._query_by_type(vec, "ramban",  1)
            )
        elif intent == "rashi":
            chunks = (
                self._query_by_type(vec, "rashi",   2) +
                self._query_by_type(vec, "chumash", 1)
            )
        elif intent == "ramban":
            chunks = (
                self._query_by_type(vec, "ramban",  2) +
                self._query_by_type(vec, "chumash", 1)
            )
        elif intent == "chumash":
            chunks = self._query_by_type(vec, "chumash", k)
        else:
            # general — top-k ללא סינון
            result = self.collection.query(
                query_embeddings=vec,
                n_results=k,
                include=["metadatas", "distances", "documents"],
            )
            chunks = [
                {
                    "meta":       meta,
                    "distance":   dist,
                    "similarity": round(1 - dist, 4),
                    "document":   doc,
                }
                for meta, dist, doc in zip(
                    result["metadatas"][0],
                    result["distances"][0],
                    result["documents"][0],
                )
            ]

        chunks.sort(key=lambda x: x["similarity"], reverse=True)
        return chunks

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
        if ct == "chumash":
            header = f"[חומש] {book} {ch}:{vs}"
        elif ct == "rashi":
            header = f"[רש\"י] {book} {ch}:{vs}"
        elif ct == "ramban":
            header = f"[רמב\"ן] {book} {ch}:{vs}"
        else:
            header = f"[{ct}/{cmt}] {book} {ch}:{vs}"

        # גוף — רק השורות הרלוונטיות, מקסימום 400 תווים
        lines = chunk["document"].split("\n")
        body_lines = [l for l in lines[1:] if l.strip()]
        body = "\n".join(body_lines[:3])  # מקסימום 3 שורות
        if len(body) > 400:
            body = body[:400].rsplit(" ", 1)[0] + "..."

        return f"{header}\n{body}"

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

        # שאלה + הקשר
        user_content = f"{context}\n\n{QUERY_TEMPLATE.format(query=query)}"
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
        chunks = self.retrieve(query)
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

            if ct == "chumash":
                label = f"חומש — {book} {ch}:{vs}"
            elif ct == "rashi":
                label = f"רש\"י — {book} {ch}:{vs}"
            elif ct == "ramban":
                label = f"רמב\"ן — {book} {ch}:{vs}"
            else:
                label = f"{ct}/{cmt} — {book} {ch}:{vs}"

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
