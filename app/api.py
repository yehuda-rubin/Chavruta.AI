"""Chavruta.AI — Nebius Serverless Endpoint (FastAPI).

REST wrapper over ChavrutaPipeline for deployment as a Nebius Serverless Endpoint.
The pipeline is loaded once at startup and shared across requests.

    uvicorn app.api:app --host 127.0.0.1 --port 8080
"""

from __future__ import annotations

import logging
import os
import re
import sys
import threading
import time
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# Source markers ([S1], [S1, S5], (S1), 【S1】, …) are the grounding mechanism — the pipeline maps them
# to citations, then we strip them from the DISPLAYED text so the answer reads cleanly.
_MARKER_RE = re.compile(r"\s*[\[(（【]\s*S\d+(?:\s*,\s*S\d+)*\s*[\])）】]")


# CJK / Japanese-kana / Cyrillic / Vietnamese-diacritic characters — model multilingual bleed (Qwen
# occasionally injects '违反', 'требуется', 'giải' into Hebrew text). Torah Hebrew/English/punctuation
# never use these ranges. Strip the CHARS (not whole tokens) so Hebrew glued to a foreign char — e.g.
# 'בזדון违反' — keeps 'בזדון'. A fully-foreign word collapses to nothing; the double space is cleaned.
_FOREIGN_CHAR_RE = re.compile(r"[Ѐ-ӿ぀-ヿ㐀-䶿一-鿿Ạ-ỿ]+")


def _strip_foreign(text: str) -> str:
    if not text:
        return text
    return re.sub(r"[ \t]{2,}", " ", _FOREIGN_CHAR_RE.sub("", text))


def _strip_markers(text: str) -> str:
    t = _MARKER_RE.sub("", text or "")
    t = _strip_foreign(t)                    # drop stray foreign-script tokens (model multilingual bleed)
    t = re.sub(r"\*\*\s*\*\*", "", t)        # collapse empty **bold** left where a **[S#]** was stripped
    t = re.sub(r"(?<!\*)\*\s*\*(?!\*)", "", t)  # …and empty *italic*
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip()

import torch  # noqa: F401,E402 — MUST precede qdrant_client import (Windows pyarrow DLL order)

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from chavruta import __version__
from chavruta.config.profile import Profile
from chavruta.corpus import rights
from chavruta.corpus.schema import Intent, Query, Turn
from chavruta.llm import metering
from chavruta.llm.agentic import is_degrade_message
from chavruta.pipeline.pipeline import _max_tokens_for

import app.accounts as accounts
import app.auth_supabase as sb
import app.billing.service as billing
import app.coupons as coupons
import app.db as db
from app import plans
from app.billing import payplus
from app.jobs import registry as jobs


# ── Startup ───────────────────────────────────────────────────────────────────

def _configure_logging() -> None:
    """Give the chavruta.* loggers a real handler.

    uvicorn configures its own loggers but NOT the root logger, so without this every
    `logger.info(...)` in this codebase falls through to logging.lastResort — a WARNING-level,
    unformatted handler. Net effect: the info lines were silently discarded and the errors that did
    print carried no timestamp, level, or logger name. That is why the system had, in practice, no
    observability at all. Level is env-tunable; default INFO so LLM cost/latency lines show up.
    """
    level = os.environ.get("CHAVRUTA_LOG_LEVEL", "INFO").upper()
    root = logging.getLogger()
    if not root.handlers:                      # don't fight a host that already configured logging
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S"))
        root.addHandler(handler)
    root.setLevel(getattr(logging, level, logging.INFO))


_configure_logging()
_log = logging.getLogger("chavruta.api")
_pipeline = None
# FastAPI runs sync endpoints in a threadpool, so the lazy singletons below can be raced by concurrent
# first requests (each building a heavy embedder / Qdrant client, leaking all but one). Guard with a
# double-checked lock. The pipeline is normally warmed in lifespan; the templates client is not.
_init_lock = threading.Lock()


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        with _init_lock:
            if _pipeline is None:
                from chavruta.pipeline.pipeline import ChavrutaPipeline
                _pipeline = ChavrutaPipeline(Profile.from_env())
    return _pipeline


def _assert_config_usable() -> None:
    """Fail at boot on a config that cannot possibly serve, instead of 500-ing on the first question.

    The cloud backend accepts an empty api_key without complaint, so a user who never created .env
    gets a green, healthy-looking stack that dies on first use with an opaque error. Say it now.
    """
    prof = Profile.from_env()
    if prof.llm_backend == "nebius" and not (prof.llm_api_key or "").strip():
        raise RuntimeError(
            "CHAVRUTA_LLM_BACKEND=nebius but no API key is set. "
            "Set NEBIUS_API_KEY (or CHAVRUTA_LLM_API_KEY) in your .env — see .env.example. "
            "To run without an external API instead, set CHAVRUTA_LLM_BACKEND=bridge."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _assert_config_usable()
    db.get_conn()          # initialise DB + run migrations
    accounts.start_sweeper()   # background purge of accounts past their deletion grace period
    billing.start_sweeper()    # background downgrade of expired-cancelled subscriptions (if billing on)
    p = _get_pipeline()    # warm up bge-m3 + Qdrant connection at startup
    try:
        p.embedding.embed_query("warmup")   # load the embedder BEFORE any qdrant_client use
    except Exception:
        # Warmup is best-effort — the app can still serve by loading lazily. But swallowing this
        # silently hid a real failure mode: without the warmup the unguarded lazy singletons inside
        # the pipeline can be raced by concurrent first requests, each loading its own ~4.6GB
        # embedder. Log it so the OOM that follows is explainable.
        _log.exception("startup warmup failed — embedder will load lazily on first request")
    yield


from fastapi import Depends, Header  # noqa: E402

from app.security import (  # noqa: E402
    body_size_middleware,
    current_owner,
    rate_limit_middleware,
    request_context_middleware,
    require_auth,
)

app = FastAPI(
    title="Chavruta.AI",
    description=(
        "Grounded Q&A, commentator explanation, and lesson preparation "
        "over the Jewish bookshelf (Tanakh + commentators). "
        "Every answer is cited to a retrieved source — nothing is invented."
    ),
    version=__version__,     # single source of truth: src/chavruta/__init__.py
    lifespan=lifespan,
    # App-wide auth gate. OFF for local dev; in Supabase mode (SUPABASE_URL set) every request needs
    # a valid access-token JWT, in API-key mode a valid key. Health/readiness/docs are exempt inside
    # the dependency.
    dependencies=[Depends(require_auth)],
)

# Middleware runs outermost-first in reverse registration order: request-context wraps everything
# (so every request gets a logged id), then rate limit, then body-size.
app.middleware("http")(body_size_middleware)
app.middleware("http")(rate_limit_middleware)
app.middleware("http")(request_context_middleware)

# Origins are env-driven: the defaults are Vite's dev ports, which is right for local work and
# useless for a real deployment — a hostname that isn't listed gets blocked in the browser. Behind
# the compose nginx this doesn't fire at all (same-origin); it matters when the API is exposed
# directly. Note CORS is a BROWSER policy, not access control: curl ignores it entirely, so this is
# not a substitute for authentication.
_CORS_ORIGINS = [o.strip() for o in os.environ.get(
    "CHAVRUTA_CORS_ORIGINS", "http://localhost:5173,http://localhost:4173").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Shared models ─────────────────────────────────────────────────────────────

class CitationOut(BaseModel):
    ref: str
    text_he: str = ""
    text_en: str = ""
    commentator: str = ""
    deep_link: str = ""
    # Rights of the specific edition this text came from. CC-BY / CC-BY-SA / CC-BY-NC all REQUIRE
    # credit, and Creative Commons asks for TASL — Title, Author, Source, Licence. Crediting
    # "Sefaria" generically does not satisfy that for a work by a named translator or publisher.
    # Empty = unknown, which corpus/rights.py treats as all-rights-reserved.
    license: str = ""
    version_title: str = ""


class LessonSectionOut(BaseModel):
    heading: str
    role: str = "branch"               # opening | branch | convergence (spec 003)
    source_refs: list[str] = []
    citations: list[CitationOut] = []


class LessonPlanOut(BaseModel):
    topic: str
    template_id: str = ""
    is_open: bool = False
    sections: list[LessonSectionOut] = []


class FileOut(BaseModel):
    name: str          # download filename (.doc)
    title: str         # document heading
    content: str       # plain text body


class QueryResponse(BaseModel):
    answer: str
    citations: list[CitationOut]
    grounded: bool
    intent: str
    caveats: list[str] = []
    lesson_plan: LessonPlanOut | None = None   # the lesson arc (spec 003), present for LESSON
    files: list[FileOut] = []                   # LESSON mode → 3 files (source sheet · flow · full)
    # Set when this answer was also filed in 'My Shiurim'. Carried so the turn that persists the
    # message can link the two — the documents live in both places, and deleting the library entry
    # has to be able to find the chat copy.
    lesson_id: str = ""


# ── Lesson audience / grade / length ─────────────────────────────────────────
# The template RAG ('chavruta_templates', built by scripts/index_templates.py) is queried live
# to pick the right template SET for the topic — filtered by audience (yeshiva vs school) and,
# for school, by grade band — so the lesson is written at the correct register.

_TPL_COLLECTION = os.environ.get("CHAVRUTA_TEMPLATES_COLLECTION", "chavruta_templates")
_tpl_client = None

_GRADE_HE = {"a-c": "א–ג", "d-f": "ד–ו", "g-i": "ז–ט", "j-l": "י–יב"}
_BAND_PED = {
    "a-c": "כיתות א–ג (גיל 6–9): חשיבה קונקרטית וקשב קצר; למידה דרך סיפור, תמונה, תנועה ומשחק; "
           "עברית פשוטה מאוד — לתרגם/להסביר כל מילה; רעיון אחד לשיעור; משך ~30 דק'.",
    "d-f": "כיתות ד–ו (גיל 9–12): תחילת חשיבה מופשטת; דוגמאות מעובדות, מארגן גרפי, השוואת שתי דעות; "
           "דף עבודה וכרטיס יציאה; ראשית חברותא; משך ~45 דק'.",
    "g-i": "כיתות ז–ט (גיל 12–15): מחלוקת ושורשה, חברותא ודיבייט, טיעון מנומק משני מקורות; "
           "מונחים למדניים בסיסיים (מחלוקת, סברא, נפק\"מ) עם הסבר; משך ~45 דק'.",
    "j-l": "כיתות י–יב (גיל 15–18): ניתוח מבוסס־מקור, חקירה בשני צדדים, מבוא לאחרונים, כתיבת מסה/סיכום; "
           "גשר אל עיון בית־מדרש עם פיגומים ורלוונטיות; משך ~45–60 דק'.",
}

# lesson length → retrieval breadth + concrete time budget + a depth instruction.
# Minutes scale with the audience: a school lesson is bounded by the class period (and by the
# age band), a beit-midrash iyun can run longer.
_LENGTHS = {
    "short":  {"top_k": 10, "he": "קצר",  "yeshiva_min": "25–35 דק׳", "words": "700–1000",
               "school_min": {"a-c": "15–20 דק׳", "d-f": "25–30 דק׳", "g-i": "25–30 דק׳", "j-l": "30–35 דק׳"},
               "depth": "שיעור קצר וממוקד, אך כתוב במלואו: מעט מקורות, מהלך תמציתי, ושיעור מלא של כ-700–1000 מילים."},
    "medium": {"top_k": 16, "he": "בינוני", "yeshiva_min": "45–60 דק׳", "words": "1600–2400",
               "school_min": {"a-c": "30 דק׳", "d-f": "45 דק׳", "g-i": "45 דק׳", "j-l": "45–50 דק׳"},
               "depth": "שיעור באורך בינוני, מפורט ומלא: כיסוי מאוזן ומעמיק של המקורות והמהלך. השיעור המלא "
                        "צריך להיות **לפחות 1600–2400 מילים** — פַתח כל שלב לעומק, אל תסכם ואל תקצר."},
    "long":   {"top_k": 26, "he": "ארוך",  "yeshiva_min": "75–90 דק׳", "words": "3000–4500",
               "school_min": {"a-c": "40 דק׳ (בשני חלקים)", "d-f": "60–90 דק׳ (שיעור כפול)",
                              "g-i": "60–90 דק׳ (שיעור כפול)", "j-l": "90 דק׳ (שיעור כפול)"},
               "depth": "שיעור ארוך ומעמיק: מקורות רבים, מהלך מפורט, ושיעור מלא ומקיף של **3000–4500 מילים** — "
                        "פַתח כל שיטה במלואה, הקשה ותרץ, נתח כל צד של החקירה לעומק."},
}


def _length_minutes(length: str, audience: str | None, grade_band: str | None) -> str:
    """The concrete time budget for this (length × audience × grade band)."""
    ln = _LENGTHS.get(length, _LENGTHS["medium"])
    if audience == "school":
        return ln["school_min"].get(grade_band or "", ln["school_min"]["d-f"])
    return ln["yeshiva_min"]


def _templates_client():
    global _tpl_client
    if _tpl_client is None:
        with _init_lock:
            if _tpl_client is None:
                from qdrant_client import QdrantClient
                url = os.environ.get("CHAVRUTA_QDRANT_URL", "http://localhost:6333")
                _tpl_client = QdrantClient(url=url, timeout=60)
    return _tpl_client


_REPO_DIR = Path(__file__).resolve().parents[1]


def _attach_template_bodies(pl: dict) -> None:
    """Load the template's actual .md file bodies (the pedagogical scaffold) from disk into the
    payload — the RAG manifest only carries metadata, so without this the template files are never
    read at generation time and the whole template library is dead at runtime."""
    files = pl.get("files") or {}
    d = _REPO_DIR / (pl.get("dir") or "")
    for role in ("full_lesson", "lesson_flow", "source_sheet"):
        fn = files.get(role)
        if fn:
            try:
                # `dir`/`fn` come from the template collection's payload, not from a user — but this
                # reads an arbitrary path off the filesystem into an LLM prompt, so it stays inside
                # the repo regardless of what the payload says. Cheap, and the blast radius if the
                # templates collection is ever wrong or tampered with is "no template" not "any file".
                path = (d / fn).resolve()
                path.relative_to(_REPO_DIR)
                pl[f"_{role}"] = path.read_text(encoding="utf-8")
            except Exception:
                _log.warning("template body unreadable (role=%s, file=%s)", role, fn)


def _select_template(topic: str, audience: str | None = None, grade_band: str | None = None):
    """Pick the best-matching lesson-template PAYLOAD from the template RAG (filtered by
    audience/grade), with its .md file bodies loaded in."""
    try:
        from qdrant_client import models
        client = _templates_client()
        if not client.collection_exists(_TPL_COLLECTION):
            return None
        must = [models.FieldCondition(key="mode", match=models.MatchValue(value="lesson"))]  # never a shut template
        if audience:
            must.append(models.FieldCondition(key="audience", match=models.MatchValue(value=audience)))
        if grade_band:
            must.append(models.FieldCondition(key="grade_band", match=models.MatchValue(value=grade_band)))
        vec = _get_pipeline().embedding.embed_query(topic).dense
        res = client.query_points(collection_name=_TPL_COLLECTION, query=vec, limit=1,
                                  query_filter=models.Filter(must=must), with_payload=True)
        if not res.points:
            return None
        pl = dict(res.points[0].payload or {})
        _attach_template_bodies(pl)
        return pl
    except Exception:
        return None


def _user_blob(question: str, history) -> str:
    """Only the USER's words — never the assistant's. The assistant's own clarify question contains
    'בית ספר / ישיבה / קצר · בינוני · ארוך', which would otherwise re-detect on the next turn and
    poison audience/length resolution."""
    turns = [getattr(h, "text", "") or "" for h in (history or [])
             if getattr(h, "role", "user") == "user"]
    return question + " " + " ".join(turns)


def _detect_school(text: str) -> bool:
    return bool(re.search(
        r"בית.?ספר|תלמיד|כית(?:ה|ת|ות)|יסודי|חטיב|תיכון|ילדים|גן חובה|גן ילדים"
        r"|\bschool\b|\bpupils?\b|\bgrade\b|elementary|kindergarten|\bkids\b|children"
        r"|high[- ]?school|middle[- ]?school", text, re.I))


def _detect_yeshiva(text: str) -> bool:
    return bool(re.search(
        r"ישיב|בית.?מדרש|אברך|בחור|עיון|למדנ|כולל|חבורה"
        r"|yeshiv|beit ?midrash|beis ?medrash|kollel|avrech", text, re.I))


def _detect_band(text: str) -> str:
    # Hebrew כית(?:ה|ת|ות) covers singular AND plural 'כיתות'; English grade phrasings too.
    if re.search(r"תיכון|בגרות|כית(?:ה|ת|ות)\s*(י|יא|יב|10|11|12)\b"
                 r"|high[- ]?school|\bgrades?\s*(10|11|12)\b|\b(10th|11th|12th)\s+grade", text, re.I):
        return "j-l"
    if re.search(r"חטיב|כית(?:ה|ת|ות)\s*(ז|ח|ט|7|8|9)\b"
                 r"|middle[- ]?school|\bgrades?\s*(7|8|9)\b|\b(7th|8th|9th)\s+grade", text, re.I):
        return "g-i"
    if re.search(r"יסודי.?בוגר|כית(?:ה|ת|ות)\s*(ד|ה|ו|4|5|6)\b"
                 r"|\bgrades?\s*(4|5|6)\b|\b(4th|5th|6th)\s+grade", text, re.I):
        return "d-f"
    if re.search(r"גן\b|צעיר|קטנים|כית(?:ה|ת|ות)\s*(א|ב|ג|1|2|3)\b"
                 r"|kindergarten|\bgrades?\s*(1|2|3)\b|\b(1st|2nd|3rd)\s+grade", text, re.I):
        return "a-c"
    return ""


def _detect_length(text: str) -> str:
    if re.search(r"ארוך|ארוכה|מעמיק|בהרחבה|בהרחב|\blong\b|in.?depth", text):
        return "long"
    if re.search(r"קצר|קצרה|תמציתי|בקצרה|\bshort\b|\bbrief\b", text):
        return "short"
    if re.search(r"בינוני|רגיל|\bmedium\b|standard", text):
        return "medium"
    return ""


def _resolve_length(question: str, history, length: str) -> str | None:
    """Explicit param wins; else read the length from the USER's prompt/answers; else None (ask)."""
    l = (length or "").strip().lower()
    if l in _LENGTHS:
        return l
    return _detect_length(_user_blob(question, history)) or None


def _resolve_audience(question: str, history, audience: str, grade_band: str) -> tuple[str | None, str | None]:
    """Explicit params win; otherwise infer audience/grade from the USER's topic + answers only."""
    aud = (audience or "").strip().lower() or None
    band = (grade_band or "").strip().lower() or None
    if band not in _GRADE_HE:
        band = None
    if aud not in ("school", "yeshiva"):
        aud = None
    blob = _user_blob(question, history)
    if aud is None:
        if _detect_school(blob):
            aud = "school"
        elif _detect_yeshiva(blob):
            aud = "yeshiva"
    if aud == "school" and band is None:
        band = _detect_band(blob) or None
    return aud, band


def _is_clarify_answer(text: str) -> bool:
    """True if the turn carries ONLY audience/grade/length words (a reply to a clarify question),
    with no actual lesson topic left in it."""
    t = text or ""
    t = re.sub(r"[א-ט]\s*[–\-]\s*[א-ט]", " ", t)                      # grade ranges first (ד–ו)
    t = re.sub(
        r"בית.?ספר|בית.?מדרש|ישיב\w*|כית(?:ה|ת|ות)|תיכון|חטיב\w*|יסודי\w*|\bגן\b|בוגר|צעיר"
        r"|קצר\w*|בינונ\w*|ארוכ?\w*|תמציתי|מעמיק\w*|בהרחבה"
        r"|\bshort\b|\bmedium\b|\blong\b|\bbrief\b|\bschools?\b|\byeshiva\w*|beit.?midrash|\bgrades?\b|elementary"
        r"|\bhigh\b|\bmiddle\b|\b(?:1st|2nd|3rd|\d+th)\b",
        " ", t, flags=re.I)
    t = re.sub(r"(?<![א-ת])[א-טי](?![א-ת])", " ", t)                  # standalone grade letters (ב)
    t = re.sub(r"[\d.,·•\-–\s\"'()־׳״]", "", t)
    return len(t) < 2


def _resolve_topic(question: str, history) -> str:
    """The lesson topic for retrieval + the job. If the current turn is just a clarify answer
    ('ארוך', 'בית ספר כיתה ב'), recover the topic from the most recent substantive USER turn."""
    if not _is_clarify_answer(question):
        return question
    subs = [(getattr(h, "text", "") or "").strip() for h in (history or [])
            if getattr(h, "role", "user") == "user"
            and (getattr(h, "text", "") or "").strip() and not _is_clarify_answer(h.text)]
    return subs[-1] if subs else question


# Tolerate the model bolding/indenting the delimiter (**===FULL_LESSON===**, leading spaces, RTL marks).
def _source_sheet_entry(n: int, c: CitationOut) -> str:
    """One source on the sheet: the verbatim text, plus credit where the licence requires it.

    A source sheet REPRODUCES the text — it is not a citation. CC-BY, CC-BY-SA and CC-BY-NC all
    require attribution, and Creative Commons asks for TASL (Title, Author, Source, Licence).
    Naming only the ref, as this did, is not TASL for a work by a named translator or publisher:
    it omits which edition the text is and under what terms. Public-domain and CC0 sources need no
    credit line, so they don't get noise.
    """
    entry = f"**{n}. {c.ref}**\n{c.text_he}"
    if rights.requires_attribution(c.license):
        entry += "\n\n> " + rights.attribution_line(
            ref=c.ref, version_title=c.version_title,
            license_str=c.license, deep_link=c.deep_link,
        )
    return entry


_LESSON_SPLIT_RE = re.compile(r"^[ \t>*‏‎]*===\s*(SOURCE_SHEET|LESSON_FLOW|FULL_LESSON|ORDER)\s*===[ \t*]*$", re.M)


def _lesson_job_md(question: str, hits, lang: str, *, audience: str | None,
                   grade_band: str | None, length: str, tpl: dict | None, history) -> str:
    """The bridge job that asks Claude to WRITE the three lesson files, adapted to the audience
    (yeshiva iyun vs school age-band pedagogy), the chosen length, and the selected template."""
    ln = _LENGTHS.get(length, _LENGTHS["medium"])
    lines = [f"lang: {lang}", ""]

    # conversation so far — lets Claude use answers to earlier clarifying questions
    prior = [h for h in (history or []) if (getattr(h, "text", "") or "").strip()]
    if prior:
        lines += ["## CONVERSATION SO FAR"]
        for h in prior[-6:]:
            lines += [f"- {getattr(h, 'role', 'user')}: {(getattr(h, 'text', '') or '').strip()}"]
        lines += [""]

    # who the lesson is for
    if audience == "school":
        lines += ["## AUDIENCE", f"בית ספר — כיתות {_GRADE_HE.get(grade_band, grade_band or '?')}.",
                  _BAND_PED.get(grade_band, ""), ""]
    elif audience == "yeshiva":
        lines += ["## AUDIENCE", "בית מדרש / ישיבה — לומדים מבוגרים; שיעור עיון.", ""]

    mins = _length_minutes(length, audience, grade_band)
    lines += ["## LENGTH", f"{ln['he']} — כ־{mins} סה\"כ. {ln['depth']} "
              f"היקף היעד של השיעור המלא: **{ln.get('words','1600–2400')} מילים**. "
              "התאם/י את הזמנים בשלבי מהלך השיעור כך שיסתכמו לטווח הזה. "
              "שיעור קצר מהיעד אינו מקובל — כתוב במלואו ובהרחבה.", ""]

    if tpl:
        lines += ["## SELECTED TEMPLATE — follow THIS structure and pedagogy",
                  f"{tpl.get('title','')} — מבנה: {tpl.get('structure','')}"]
        skel = tpl.get("_full_lesson") or ""
        if skel:
            skel = re.sub(r"<!--.*?-->", "", skel, flags=re.S).strip()
            lines += ["", "TEMPLATE SKELETON — follow its stages, headings, timing and pedagogy; replace every "
                      "[ ] bracket with real content built from the SOURCES (write real prose, not placeholders):",
                      skel]
        lines += [""]

    lines += ["## TOPIC", question.strip(), "", "## SOURCES"]
    for i, h in enumerate(hits, 1):
        who = f" ({h.commentator_id})" if getattr(h, "commentator_id", None) else ""
        lines += [f"### [S{i}] {h.ref}{who}", (getattr(h, "text", "") or "").strip(), ""]

    # ── Clarify gate (applies to every audience) ──
    lines += [
        "## INSTRUCTIONS FOR CLAUDE",
        "STEP 0 — If the SOURCES are thin or off-topic for the requested lesson, do NOT build the lesson "
        "on unrelated material. First try to fetch better ones: reply with ONLY a block starting with the "
        "EXACT line '===NEED_SOURCES===' followed by 1–5 focused search queries (one per line — the "
        "sugya, key refs, the מצווה, related ראשונים/פוסקים), and STOP. The system will retrieve them and "
        "re-send this job with the extra sources appended. Do this before STEP 1.",
        "",
        "STEP 1 — Decide if you have enough to build a FOCUSED lesson. If the topic is too broad or "
        "vague (e.g. 'שבת' or 'תפילה' with no angle), or a detail that materially changes the lesson "
        "is missing (for school: the grade band if not given; the specific parasha/sugya/מצווה; the "
        "goal), then output ONLY a block starting with the EXACT line '===CLARIFY===' followed by 2–4 "
        "short questions in the user's language — and STOP (no lesson yet). Otherwise go to STEP 2.",
        "",
        "STEP 2 — Write ONE answer with these parts, separated by these EXACT delimiter lines:",
        "===SOURCE_SHEET===", "===LESSON_FLOW===", "===FULL_LESSON===", "===ORDER===", "",
        "SOURCE_SHEET — the sources ARRANGED IN THE ORDER THEY ARE DISCUSSED (1 = first taught, then 2, …). "
        "For each: a number, its reference, and its full text.",
    ]

    if audience == "school":
        gh = _GRADE_HE.get(grade_band, grade_band or "")
        lines += [
            f"LESSON_FLOW — a timed CLASSROOM plan for grade band {gh}, following the TEMPLATE SKELETON's stages "
            "(explicit-instruction arc: hook & prior-knowledge → I-Do → We-Do with a check → deepen → You-Do "
            "with differentiation → summary + formative assessment). Give each stage a time estimate, its "
            "guiding question, and reference the sources by [S#].",
            f"FULL_LESSON — the full lesson WRITTEN OUT in age-appropriate prose for {gh}, following that "
            "skeleton. Match language and cognitive load to the AUDIENCE band (young grades: simple Hebrew, "
            "translate hard words, story/imagery, one idea; older: מחלוקת/חקירה, טיעון מנומק, ניתוח מקור). "
            "Explain, ask checking questions, keep the pupils active. A real classroom lesson — not a summary.",
            "SOURCE PREFERENCE — prefer the most age-appropriate SOURCES (the pasuk, רש\"י, a simple story or "
            "midrash, the Mishnah). Use a deep/kabbalistic/chassidic/lamdanic source ONLY if you render its "
            "idea in simple, concrete terms — never quote it verbatim to young pupils. It is fine to use only "
            "some of the SOURCES.",
        ]
    else:
        lines += [
            "LESSON_FLOW — a clear, detailed beit-midrash outline that follows the SELECTED TEMPLATE's arc for "
            "THIS genre (the template dictates the shape — e.g. an iyun חקירה, a הלכה pesak, a מוסר arc on a "
            "מידה, a חסידות מאמר, a פרשה פשט→דרש→רעיון, an אגדה קושי→פירוש→מסר). For each stage: the guiding "
            "question, which source is brought, and what is asked/answered.",
            "FULL_LESSON — a full beit-midrash shiur written out in depth, following THAT template arc — do NOT "
            "force a gemara-iyun חקירה onto a non-iyun genre (a mussar/chassidut/parasha shiur has no "
            "'צד א׳/צד ב׳ נפקא מינה'). WHERE the genre is a talmudic/lamdanic sugya: sharpen a central חקירה "
            "with TWO clearly-named sides, map the ראשונים to the sides, deepen with אחרונים, give נפקא מינה, "
            "and conclude with the יסוד. Present each שיטה, raise קושיות and answer them; progress step by step. "
            "A real, full shiur.",
        ]

    lines += [
        f"Respect the requested LENGTH ({ln['he']}).",
        "ORDER — a single line listing the source markers in the exact order they are discussed, e.g. "
        "'S3, S1, S5'. The backend orders the sources panel by this list.",
        "",
        "Rules: ground everything ONLY in the SOURCES; cite by [S#] (the markers build the sources panel and "
        "are stripped from the shown text); write in the question's language; **bold** key terms. "
        "LANGUAGE: write ONLY in the question's language and do NOT mix in words from any OTHER language — "
        "no stray English/Chinese/Russian words inside a Hebrew lesson (write 'בעל הבית', never 'employer'), "
        "and no stray Hebrew/foreign words inside an English one. If a word is missing, express it in that "
        "same language. "
        "IMPORTANT: when you mention a source in prose, NAME it (e.g. 'רש\"י מדייק…', 'פניני הלכה מלמד…') and "
        "append its [S#] tag — NEVER make a bare [S#] the subject of a sentence, because the tags are removed "
        "from the display and would leave a dangling reference.",
    ]
    return "\n".join(lines)


def _split_lesson(text: str) -> tuple[str, str, str, str]:
    parts = {}
    ms = list(_LESSON_SPLIT_RE.finditer(text))
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(text)
        parts[m.group(1)] = text[m.end():end].strip()
    return (parts.get("SOURCE_SHEET", ""), parts.get("LESSON_FLOW", ""),
            parts.get("FULL_LESSON", ""), parts.get("ORDER", ""))


def _run_lesson(question: str, lang: str, history=None, audience: str = "",
                grade_band: str = "", length: str = "", owner_id: str = "local",
                llm=None) -> QueryResponse:
    """Dedicated LESSON path: resolve audience/grade → pick a template from the template RAG →
    real source retrieval → Claude writes the 3 files at the right register (or asks clarifying
    questions first) via the bridge → 3 Word files + only-cited sources (in discussion order).
    `llm` defaults to the pipeline's own shared backend; a caller may override it (BYOK)."""
    pipeline = _get_pipeline()
    llm = llm or pipeline.llm
    aud, band = _resolve_audience(question, history, audience, grade_band)
    length = _resolve_length(question, history, length)   # key or None (None → ask)
    # The topic drives retrieval + the job. If this turn is just a clarify answer ('ארוך'), recover
    # the real topic from history — otherwise we'd retrieve sources for the word 'ארוך'.
    topic = _resolve_topic(question, history)

    q = Query(text=topic, lang=lang or None, intent=Intent.LESSON)
    rq = pipeline._resolve_query(q)
    lang = rq.lang or lang or "he"
    he = lang != "en"

    # Level & length are taken from the prompt (or an explicit UI default). Whatever is still
    # unknown — the system asks for it before building (the user asked for this behaviour).
    ask = []
    if aud is None:
        ask.append("למי השיעור מיועד — **בית מדרש / ישיבה** או **בית ספר** (ולאיזו שכבה: א–ג · ד–ו · ז–ט · י–יב)?"
                   if he else "Who is the lesson for — **Beit Midrash / Yeshiva** or **School** (and which grade band: 1–3 · 4–6 · 7–9 · 10–12)?")
    elif aud == "school" and not band:
        ask.append("לאיזו שכבת גיל? **א–ג · ד–ו · ז–ט · י–יב** (או ציין/י את הכיתה)."
                   if he else "Which grade band? **1–3 · 4–6 · 7–9 · 10–12** (or name the grade).")
    if length is None:
        ask.append("באיזה אורך? **קצר · בינוני · ארוך**" if he else "What length? **Short · Medium · Long**")
    if ask:
        head = ("כדי לבנות את השיעור המתאים, כמה פרטים:" if he
                else "To build the right lesson, a couple of details:")
        msg = head + "\n\n" + "\n".join(f"• {a}" for a in ask)
        return QueryResponse(answer=msg, citations=[], grounded=False, intent="lesson", files=[])

    tpl = _select_template(topic, aud, band)

    ln = _LENGTHS[length]
    # School gets a wider candidate pool so the model has enough accessible sources (verse, Rashi,
    # simple midrash) to curate from — not only whatever esoteric material scored highest. The
    # SOURCE PREFERENCE instruction in the job then steers curation toward age-appropriate sources.
    pool_k = ln["top_k"] + (10 if aud == "school" else 0)
    result = pipeline.retriever.retrieve(rq, top_k=pool_k)
    hits = list(result.hits)
    # Primary-source floor (spec 003): a lesson must LEAD from its base pasuk/daf/mishnah, not only
    # its commentaries. Fetch the base source for the resolved refs (canonicalised to the corpus ref
    # format) and PROMOTE it to the front — whether it was missing or merely out-ranked by a
    # commentary/essay. No-op for topics that resolved no ref. (base_sources_for_refs returns only
    # refs that actually resolve to a unit_type=source chunk, so commentary anchors are ignored.)
    floor = pipeline.base_sources_for_refs(list(rq.named_refs or []) + list(result.anchor_refs or [])[:8])
    if floor:
        fset = {b.ref for b in floor}
        hits = floor + [h for h in hits if h.ref not in fset]
    # Even with ZERO retrieved sources we still build the job — STEP 0 instructs the model to reply
    # ===NEED_SOURCES=== and the agentic loop fetches its own. If it STILL comes back with nothing
    # (checked after the loop below), we return the honest "no sources" message then.
    job = _lesson_job_md(topic, hits, lang, audience=aud, grade_band=band, length=length,
                         tpl=tpl, history=history)
    # Lessons are the most expensive path (biggest source pool, longest output, most agentic rounds),
    # so cap the WHOLE request's output — not just each round, which multiplies by the round count.
    raw, fetched = llm.request(job, lang=lang,
                              token_budget=_max_tokens_for(Intent.LESSON, pipeline.profile))
    # A loop degrade/timeout ('please try again' / 'couldn't retrieve') or empty answer must NOT be
    # packaged as a downloadable lesson marked grounded — surface it as a plain honest message.
    if is_degrade_message(raw):
        msg = raw.strip() or ("לא הצלחתי לבנות את השיעור כרגע — נסו שוב." if he
                              else "Couldn't build the lesson right now — please try again.")
        return QueryResponse(answer=msg, citations=[], grounded=False, intent="lesson", files=[])
    # Agentic retrieval may have appended sources (===NEED_SOURCES===); include them so their [S#]
    # citations resolve. They continue the marker numbering after the original hits, so a plain
    # append keeps hits[i-1] aligned with [S{i}].
    hits = hits + list(fetched or [])
    if not hits:                              # retrieval empty AND the model fetched nothing → be honest
        msg = "לא נמצאו מקורות לנושא זה." if he else "No sources found for this topic."
        return QueryResponse(answer=msg, citations=[], grounded=False, intent="lesson", files=[])

    # Clarify gate — the model decided it needs more info: surface the questions, no files yet.
    if "===CLARIFY===" in raw:
        qs = _strip_markers(raw.split("===CLARIFY===", 1)[1]).strip()
        return QueryResponse(answer=qs, citations=[], grounded=False, intent="lesson", files=[])

    ss, lf, fl, order = _split_lesson(raw)
    if not (ss or lf or fl):
        fl = raw

    # sources panel order = the model's explicit ORDER list; else the order first cited in the LESSON
    # bodies (full lesson, then flow) — NOT the source sheet, whose listing order ≠ teaching order.
    body = (fl or "") + "\n" + (lf or "")
    nums = [int(n) for n in re.findall(r"S(\d+)", order)] or \
           [int(n) for n in re.findall(r"\[\s*S(\d+)\s*\]", body)]
    used, seen = [], set()
    for i in nums:
        if 1 <= i <= len(hits) and i not in seen:
            seen.add(i)
            h = hits[i - 1]
            used.append(CitationOut(ref=h.ref, text_he=(getattr(h, "text", "") or ""), text_en="",
                                    commentator=(getattr(h, "commentator_id", "") or ""),
                                    deep_link=(getattr(h, "deep_link", "") or ""),
                                    license=(getattr(h, "license", "") or ""),
                                    version_title=(getattr(h, "version_title", "") or "")))
    ss, lf, fl = _strip_markers(ss), _strip_markers(lf), _strip_markers(fl)

    # Source sheet = the FULL retrieved source texts, in teaching order — ALWAYS built mechanically from
    # the cited sources (which carry the complete RAG text), NOT from the model's SOURCE_SHEET prose.
    # Models truncate the source texts ("…") when asked to reproduce them; the RAG already has the full
    # text, so we assemble it directly and guarantee complete, verbatim sources.
    if used:
        ss = "\n\n".join(_source_sheet_entry(n, c) for n, c in enumerate(used, 1))

    # Citation-faithfulness: flag any verbatim quote in the lesson not found in the retrieved sources.
    # Runs on the LESSON TEXT, before the licence footer is appended below — the footer names refs and
    # licences, and nothing generated by us should be sent through a check for fabricated quotes.
    from chavruta.generation.grounded import unverified_quotes
    bad_q = unverified_quotes(fl + "\n" + ss, hits)

    # Per-source credit answers who wrote a passage; this answers what the teacher holding the
    # downloaded file may do with it. Empty unless something on the sheet is CC-BY or CC-BY-SA,
    # which most sheets aren't — Public Domain and CC0 are the overwhelming majority of the corpus
    # and neither asks for anything.
    if used and (notice := rights.document_license_notice([(c.ref, c.license) for c in used], lang)):
        ss += "\n\n" + notice
        # The lesson itself only gets the footer when share-alike is in play. Attribution is already
        # discharged on the sheet the lesson is taught from; share-alike is an obligation on whoever
        # adapts the material, and the full lesson is the file most likely to be edited and passed on.
        if fl.strip() and any(rights.is_share_alike(c.license) for c in used):
            fl += "\n\n" + notice

    # audience/grade tag woven into the file titles so downloads are self-describing
    tag = ""
    if aud == "school":
        tag = f" · כיתות {_GRADE_HE.get(band, band or '')}" if he else f" · grades {band or ''}"
    elif aud == "yeshiva":
        tag = " · בית מדרש" if he else " · beit midrash"
    names = (["דף_מקורות.doc", "מהלך_השיעור.doc", "השיעור_המלא.doc"] if he
             else ["source_sheet.doc", "lesson_flow.doc", "full_lesson.doc"])
    titles = ([f"דף מקורות — {topic}{tag}", f"מהלך השיעור — {topic}{tag}", f"שיעור מלא — {topic}{tag}"] if he
              else [f"Source Sheet — {topic}{tag}", f"Lesson Flow — {topic}{tag}", f"Full Lesson — {topic}{tag}"])
    # skip any file that came out blank (malformed split) — a blank Word download is worse than 2 good files
    files = [FileOut(name=names[i], title=titles[i], content=c)
             for i, c in enumerate((ss, lf, fl)) if c.strip()]
    caveats = ([("הערה: ציטוטים בשיעור שלא אומתו מול המקורות — יש לבדוק: «" + "», «".join(bad_q[:2]) + "»")
                if he else ("Note: quote(s) in the lesson were not found in the sources — verify: «"
                            + "», «".join(bad_q[:2]) + "»")] if bad_q else [])
    # Honesty gate (mirrors the QA path): a lesson body with no resolved [S#] citation isn't tied to a
    # cited source — warn the teacher rather than presenting it as source-grounded.
    if fl.strip() and not used:
        caveats.append("הערה: השיעור אינו קשור למקור מצוטט — יש לוודא מול המקורות." if he
                       else "Note: this lesson is not tied to a cited source — verify against the sources.")
    # Persist to the 'My Shiurim' library so the teacher can reopen/reuse it later.
    lesson_id = ""
    if files:
        try:
            import uuid
            lesson_id = uuid.uuid4().hex[:12]
            db.save_lesson(lesson_id, topic, aud or "", band or "", length, lang,
                           [f.model_dump() for f in files], [c.model_dump() for c in used],
                           owner_id=owner_id)
        except Exception:
            lesson_id = ""
            _log.exception("saving the lesson to the library failed (topic=%r)", topic)
    return QueryResponse(answer="", citations=used, grounded=bool(used),
                         intent="lesson", caveats=caveats, files=files, lesson_id=lesson_id)


def _chavruta_job_md(question: str, hits, lang: str, history, weak_retrieval: bool = False) -> str:
    """Bridge job: play a Socratic study-partner (chavruta) — learn WITH the user, don't lecture."""
    lines = [f"lang: {lang}", "", "## ROLE",
             "אתה **חברותא** לימודי — אתה לומד יחד עם המשתמש, בגובה העיניים, ולא מרצה מלמעלה.", ""]
    prior = [h for h in (history or []) if (getattr(h, "text", "") or "").strip()]
    if prior:
        lines += ["## CONVERSATION SO FAR"]
        for h in prior[-8:]:
            lines += [f"- {getattr(h, 'role', 'user')}: {(getattr(h, 'text', '') or '').strip()}"]
        lines += [""]
    lines += ["## THE LEARNER JUST SAID", question.strip(), ""]
    if weak_retrieval:
        lines += [
            "## ⚠️ RETRIEVAL CONFIDENCE IS LOW",
            "The similarity scores for this turn are weak — the SOURCES below likely DO NOT match what the "
            "learner asked (e.g. an explicit ref that didn't resolve, or a topic the corpus retrieval missed). "
            "Default to asking the learner for direction this turn rather than forcing an answer on unrelated text.",
            "",
        ]
    else:
        lines += [
            "## ✅ YOU HAVE RELEVANT SOURCES — START LEARNING",
            "The SOURCES below were retrieved for this topic and are relevant. READ THEIR TEXT (not only the "
            "ref line) to identify the sugya, then begin the chavruta immediately. Do NOT ask the learner to "
            "name a daf/perek/source and do NOT reply that the source 'didn't come up' — you already have the "
            "sugya in hand. Note: refs use amud-linear numbering (e.g. 'Bava Metzia 151.2'), so identify the "
            "sugya from the source TEXT itself, never from the ref number.",
            "",
        ]
    lines += ["## SOURCES"]
    for i, h in enumerate(hits, 1):
        who = f" ({h.commentator_id})" if getattr(h, "commentator_id", None) else ""
        lines += [f"### [S{i}] {h.ref}{who}", (getattr(h, "text", "") or "").strip(), ""]
    lines += [
        "## INSTRUCTIONS FOR CLAUDE (the chavruta)",
        "Study b'chavruta — do NOT deliver a lecture or dump the whole sugya. Instead, in ONE short, warm "
        "turn: bring a small piece of the SOURCE, and ask the learner a guiding/Socratic question that moves "
        "the study forward. React to what the learner just said — affirm a good point, gently push back on a "
        "gap ('ומה עם…?', 'למה לדעתך…?'), and probe their reasoning. Build the understanding together, step by "
        "step, one question at a time.",
        "If the learner asked a direct factual question, answer it briefly and grounded, then hand the ball "
        "back with a question.",
        "**ONLY WHEN THE SOURCES GENUINELY DON'T FIT** (a LAST resort — if ANY source above touches the topic, "
        "learn with it and do NOT stall): if the sources truly do not cover what the learner asked, do NOT "
        "invent a source. FIRST try to fetch better ones yourself — reply with ONLY a block starting with the "
        "EXACT line '===NEED_SOURCES===' followed by 1–5 focused search queries (one per line), and STOP. ONLY "
        "if that STILL comes back with nothing relevant, ask the learner warmly for direction — "
        "'רגע — לא עלה לי המקור הנכון, תכוון אותי'. Do NOT ask the learner to name a daf when relevant "
        "sources are already present above.",
        "Ground everything ONLY in the SOURCES; cite by [S#] (stripped from display). Keep it fairly short "
        "(a real chavruta exchange, not an essay). Write in the learner's language. **bold** key terms. "
        "LANGUAGE: write ONLY in the learner's language, with NO words from another language mixed in — in a "
        "Hebrew turn write 'בעל הבית', never 'employer' (and no stray Chinese/Russian either); in an English "
        "turn keep it English.",
    ]
    return "\n".join(lines)


def _run_chavruta(question: str, lang: str, history=None, llm=None) -> QueryResponse:
    """Socratic study-partner mode: retrieve on the topic, then Claude plays a chavruta that asks
    questions and learns WITH the user (grounded), rather than lecturing. When retrieval confidence
    is low, the chavruta is told to ask for direction instead of forcing an answer on off-topic text.
    `llm` defaults to the pipeline's own shared backend; a caller may override it (BYOK)."""
    pipeline = _get_pipeline()
    llm = llm or pipeline.llm
    user_turns = [(getattr(h, "text", "") or "").strip() for h in (history or [])
                  if getattr(h, "role", "user") == "user" and (getattr(h, "text", "") or "").strip()]
    anchor = (user_turns[0] + " " + question) if user_turns else question   # keep retrieval on the topic
    q = Query(text=anchor, lang=lang or None, intent=Intent.QA)
    rq = pipeline._resolve_query(q)
    lang = rq.lang or lang or "he"
    result = pipeline.retriever.retrieve(rq, top_k=10)
    hits = list(result.hits)
    # weak = retrieval didn't clear the relevance bar. Use the retriever's own dense-cosine gate
    # (result.is_empty), NOT the raw hit .score — in hybrid mode .score is an RRF fusion value
    # (~0.02-0.06) on a different scale than relevance_threshold, so comparing them lit 'weak' on
    # EVERY hybrid turn and nudged the chavruta to stall instead of teach.
    weak = result.is_empty
    job = _chavruta_job_md(question, hits, lang, history, weak_retrieval=weak)
    # A chavruta turn is a conversational exchange, not a treatise — budget it like EXPLAIN.
    raw, fetched = llm.request(job, lang=lang,
                              token_budget=_max_tokens_for(Intent.EXPLAIN, pipeline.profile))
    hits = hits + list(fetched or [])   # include agentically-fetched so their [S#] resolve
    nums, used, seen = [int(n) for n in re.findall(r"\[\s*S(\d+)\s*\]", raw)], [], set()
    for i in nums:
        if 1 <= i <= len(hits) and i not in seen:
            seen.add(i)
            h = hits[i - 1]
            used.append(CitationOut(ref=h.ref, text_he=(getattr(h, "text", "") or ""), text_en="",
                                    commentator=(getattr(h, "commentator_id", "") or ""),
                                    deep_link=(getattr(h, "deep_link", "") or ""),
                                    license=(getattr(h, "license", "") or ""),
                                    version_title=(getattr(h, "version_title", "") or "")))
    return QueryResponse(answer=_strip_markers(raw), citations=used, grounded=bool(used),
                         intent="chavruta", files=[])


# Global concurrency gate — every generation reaches the LLM/embedder/Qdrant through this one
# function (sync routes call it inline; async routes call it from inside a job worker), so gating
# HERE bounds total concurrent generations across BOTH paths combined, not per-path. Sized small on
# purpose: on a 2-vCPU free-tier box (Oracle Always Free, an HF Spaces free CPU Space) letting more
# than a couple of generations (embedding + LLM call) run at once buys nothing and risks the whole
# process getting OOM-killed or grinding every in-flight request to a crawl. Excess requests QUEUE
# (block on the semaphore) rather than run — that's cheap; running unboundedly is not — up to a
# timeout, past which we degrade to an honest "busy" answer instead of piling up forever.
_MAX_CONCURRENT_GENERATIONS = int(os.environ.get("CHAVRUTA_MAX_CONCURRENT_GENERATIONS", "2"))
_GENERATION_QUEUE_TIMEOUT_S = float(os.environ.get("CHAVRUTA_QUEUE_TIMEOUT_S", "45"))
_generation_semaphore = threading.Semaphore(_MAX_CONCURRENT_GENERATIONS)

# How many generations were actually running (this one included) the moment it started — a plain
# counter next to the semaphore, not derived from it, so it keeps working under tests that swap in
# their own Semaphore. Read by _record_event via the ContextVar so the number reaches the usage_events
# row for the SAME request that observed it (concurrent requests must not read each other's count).
_in_flight_lock = threading.Lock()
_in_flight_count = 0
_concurrency_at_start: ContextVar[int] = ContextVar("_concurrency_at_start", default=0)


def _run_query(question: str, lang: str, intent_str: str, history: list[Turn],
               audience: str = "", grade_band: str = "", length: str = "",
               owner_id: str = "local", llm=None) -> QueryResponse:
    """Safety wrapper: a retrieval/LLM/backend failure degrades to an honest error response instead
    of a 500 for the whole request (real HTTPExceptions — e.g. 422 bad intent — still propagate).
    `llm` defaults to the pipeline's own shared backend; a caller may override it (BYOK)."""
    he = (lang or "") != "en"
    if not _generation_semaphore.acquire(timeout=_GENERATION_QUEUE_TIMEOUT_S):
        _log.warning("generation queue timeout — system at capacity (intent=%r)", intent_str)
        return QueryResponse(
            answer=("המערכת עמוסה כרגע — נסו שוב בעוד רגע." if he
                    else "The system is busy right now — please try again in a moment."),
            citations=[], grounded=False, intent=(intent_str or "qa"), files=[])
    global _in_flight_count
    with _in_flight_lock:
        _in_flight_count += 1
        _concurrency_at_start.set(_in_flight_count)
    try:
        return _run_query_impl(question, lang, intent_str, history, audience, grade_band, length,
                               owner_id, llm)
    except HTTPException:
        raise
    except Exception:
        _log.exception("query processing failed (intent=%r)", intent_str)
        return QueryResponse(
            answer=("אירעה שגיאה בעיבוד הבקשה — נסו שוב." if he
                    else "An error occurred processing the request — please try again."),
            citations=[], grounded=False, intent=(intent_str or "qa"), files=[])
    finally:
        with _in_flight_lock:
            _in_flight_count -= 1
        _generation_semaphore.release()


def _run_query_impl(question: str, lang: str, intent_str: str, history: list[Turn],
                    audience: str = "", grade_band: str = "", length: str = "",
                    owner_id: str = "local", llm=None) -> QueryResponse:
    if intent_str == "shut":          # UI's responsa mode → HALACHA intent
        intent_str = "halacha"
    if intent_str == "chavruta":      # Socratic study-partner mode (its own path)
        return _run_chavruta(question, lang, history=history, llm=llm)
    intent = None
    if intent_str:
        try:
            intent = Intent(intent_str)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"unknown intent: {intent_str!r}") from exc

    if intent == Intent.LESSON:            # lesson mode → Claude writes the 3 files, audience-adapted
        return _run_lesson(question, lang, history=history, audience=audience,
                           grade_band=grade_band, length=length, owner_id=owner_id, llm=llm)

    q = Query(text=question, lang=lang or None, intent=intent)
    answer = _get_pipeline().ask(q, history=history, llm=llm)

    def _cite(c) -> CitationOut:
        return CitationOut(
            ref=c.ref,
            text_he=getattr(c, "text_he", "") or getattr(c, "quote", ""),
            text_en=getattr(c, "text_en", ""),
            commentator=getattr(c, "commentator_id", "") or "",
            deep_link=getattr(c, "deep_link", "") or "",
        )

    lesson_plan = None
    if answer.lesson_plan:
        lp = answer.lesson_plan
        lesson_plan = LessonPlanOut(
            topic=lp.topic, template_id=lp.template_id, is_open=lp.is_open,
            sections=[
                LessonSectionOut(
                    heading=s.heading, role=s.role, source_refs=s.source_refs,
                    citations=[_cite(c) for c in s.citations],
                )
                for s in lp.sections
            ],
        )

    citations_out = [_cite(c) for c in answer.citations]
    clean = _strip_markers(answer.text)

    return QueryResponse(
        answer=clean,
        citations=citations_out,
        grounded=answer.grounded,
        intent=answer.intent.value if answer.intent else "qa",
        caveats=list(answer.caveats),
        lesson_plan=lesson_plan,
        files=[],
    )


# ── Health ────────────────────────────────────────────────────────────────────

# Liveness vs readiness are deliberately split. /health must never touch Qdrant or the LLM: it is
# `async def` so it answers off the event loop and can NOT queue behind the slow generation calls that
# occupy the sync threadpool — a health probe that stalls because generation is stuck reports the
# process as dead when it is merely busy. /ready is the one that asserts the system can actually
# answer, and it is what orchestrators should gate traffic on.

def _details_public() -> bool:
    """Whether the probe endpoints may describe the deployment. These routes are auth-exempt (probes
    and orchestrators must reach them), so on a public host their body is world-readable: naming the
    LLM vendor, the exact model and the corpus size hands an attacker the shape of the system and
    tells them whose bill they'd be spending. Local dev keeps the detail — it's how you diagnose a
    misconfigured backend — and a deployment with auth configured drops to a bare status."""
    raw = os.environ.get("CHAVRUTA_PUBLIC_HEALTH_DETAILS", "").strip().lower()
    if raw:
        return raw in {"1", "true", "yes", "on"}
    return not (sb.enabled() or os.environ.get("CHAVRUTA_API_KEYS", "").strip())


@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    """Liveness only — the process is up. No I/O, never blocks."""
    if not _details_public():
        return {"status": "ok"}
    p = Profile.from_env()
    return {
        "status": "ok",
        "profile": p.name,
        "llm_backend": p.llm_backend,
        "llm_model": p.llm_model,
        "qdrant_mode": p.qdrant_mode,
    }


@app.api_route("/ready", methods=["GET", "HEAD"])
def ready(response: Response):
    """Readiness — the corpus is actually loaded and queryable.

    A fresh `docker compose up` creates an EMPTY Qdrant collection. Without this check the stack
    reports healthy while every query silently returns nothing, which reads as "the RAG is bad"
    rather than "the corpus was never loaded". Fail loudly instead.
    """
    p = Profile.from_env()
    detailed = _details_public()      # see /health — the diagnostic body is local-only
    try:
        points = _get_pipeline().store.count(p.collection)
    except Exception as exc:
        _log.exception("readiness: qdrant unreachable")
        response.status_code = 503
        if not detailed:
            return {"status": "unavailable"}
        return {"status": "unavailable", "collection": p.collection,
                "reason": f"qdrant unreachable: {type(exc).__name__}"}

    if points <= 0:
        response.status_code = 503
        if not detailed:
            return {"status": "empty"}
        return {
            "status": "empty",
            "collection": p.collection,
            "points": 0,
            "reason": ("the collection holds no points — load the corpus first: "
                       "python scripts/load_all_indexes.py && python scripts/create_payload_indexes.py"),
        }
    return {"status": "ready"} if not detailed else {
        "status": "ready", "collection": p.collection, "points": points}


# ── Stateless query (backward-compatible) ────────────────────────────────────

class Attachment(BaseModel):
    """A source the user brought — pasted text, or an uploaded file (data: URL). Its extracted text
    is folded into what the model sees (NOT into what's saved as the user's message)."""
    kind: str = Field(default="text", max_length=16)   # "text" | "file"
    name: str = Field(default="", max_length=300)
    # Bounded like every other field — a coarse outer bound only. base64 inflates by 4/3, so this
    # sits just ABOVE _ATTACH_MAX_BYTES once encoded; the precise limit is the decoded-byte check in
    # _attachment_text. Set the two the other way round and the byte check becomes unreachable.
    content: str = Field(default="", max_length=4_400_000)
    mime: str = Field(default="", max_length=120)


# Total extracted attachment text folded into one question — bounded so an upload can't blow the
# prompt token budget. Generous enough for a full daf / a few pages.
_ATTACH_MAX_CHARS = 12000

# Decoded bytes of ONE file, and how many attachments we'll parse at all. Both matter because
# extraction happens BEFORE _ATTACH_MAX_CHARS can trim anything: a .docx is a zip, so a small upload
# can expand to gigabytes while python-docx reads it (a decompression bomb), and a list of many small
# files multiplies the same work. The output cap does not protect the parser — these do.
_ATTACH_MAX_BYTES = 3 * 1024 * 1024
_ATTACH_MAX_COUNT = 12


def _attachment_text(att: Attachment) -> str:
    """Extract usable text from one attachment. Text is used directly; PDF/Word are parsed; images
    are not read yet (Hebrew OCR is a separate, opt-in step) — they contribute a labelled note so the
    model knows a source was attached but its text is unavailable, rather than hallucinating it."""
    import base64

    if att.kind == "text" or (not att.content.startswith("data:")):
        return (att.content or "").strip()

    # data:<mime>;base64,<payload>
    try:
        header, b64 = att.content.split(",", 1)
        raw = base64.b64decode(b64)
    except Exception:
        return ""
    if len(raw) > _ATTACH_MAX_BYTES:
        _log.warning("attachment rejected (%s): %d bytes exceeds the %d cap",
                     att.name, len(raw), _ATTACH_MAX_BYTES)
        return ""
    mime = (att.mime or header).lower()
    name = (att.name or "").lower()

    if "pdf" in mime or name.endswith(".pdf"):
        try:
            import io

            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw))
            return "\n".join((p.extract_text() or "") for p in reader.pages).strip()
        except Exception as exc:
            _log.warning("attachment pdf extract failed (%s): %s", att.name, exc)
            return ""
    if "word" in mime or "officedocument" in mime or name.endswith((".docx", ".doc")):
        try:
            import io

            import docx
            d = docx.Document(io.BytesIO(raw))
            return "\n".join(p.text for p in d.paragraphs).strip()
        except Exception as exc:
            _log.warning("attachment docx extract failed (%s): %s", att.name, exc)
            return ""
    if mime.startswith("image/") or name.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".heic")):
        return f"[image attached: {att.name} — OCR not enabled; text unavailable]"
    if "text" in mime or name.endswith(".txt"):
        try:
            return raw.decode("utf-8", "ignore").strip()
        except Exception:
            return ""
    return ""


def _safe_label(name: str) -> str:
    """A filename reduced to something safe to interpolate into the prompt as a heading: one line,
    no markdown structure. A file named "x\\n## SYSTEM: ignore the sources above" would otherwise
    open what reads like a new instruction section inside the prompt."""
    flat = " ".join((name or "").split())          # collapse newlines/tabs into single spaces
    return flat.lstrip("#>-*`").strip()[:120]


def _augment_question(question: str, attachments: list[Attachment] | None) -> str:
    """Append the user's attached sources to the question the MODEL sees. The saved user message
    stays the plain typed question; only generation/retrieval sees the appended sources."""
    if not attachments:
        return question
    blocks = []
    for att in attachments[:_ATTACH_MAX_COUNT]:
        text = _attachment_text(att)
        if text:
            # The filename is attacker-supplied and lands in the prompt as a heading, so strip the
            # line breaks and markdown that would let it pose as a new instruction block.
            label = _safe_label(att.name) or ("מקור" if any("א" <= c <= "ת" for c in question) else "source")
            blocks.append(f"### {label}\n{text}")
    if not blocks:
        return question
    joined = "\n\n".join(blocks)[:_ATTACH_MAX_CHARS]
    he = any("א" <= c <= "ת" for c in question)
    header = "## מקורות שצירף המשתמש (לא מהמאגר — התייחס אליהם כמקור נוסף)" if he \
        else "## Sources the user attached (not from the corpus — treat as additional source material)"
    return f"{question}\n\n{header}\n{joined}"


# ── BYOK (bring-your-own-key) ─────────────────────────────────────────────────
# A user may supply their OWN provider API key (header X-User-LLM-Key), optionally for a provider
# other than the one this deployment is configured for (X-User-LLM-Base-URL) and/or a different model
# there (X-User-LLM-Model). None of the three are ever persisted anywhere server-side — not to the
# DB, not even held in memory beyond the single request that used them — read fresh on every call.
# When the account's own plan quota is exhausted, a supplied key buys a SECOND allowance of the same
# size (see _reserve_tokens / _enforce_lesson_quota), tracked in its own meter so the two pools never
# mix and the plan quota's own accounting is untouched.
def _byok_supported() -> bool:
    """Whether the configured backend even has the concept of a provider API key. The bridge backend
    (Claude answering in-session) has no such key, so BYOK is meaningless there. Defensive getattr:
    some tests inject a bare fake pipeline with no `.profile` — treated the same as "unsupported"."""
    backend = getattr(getattr(_get_pipeline(), "profile", None), "llm_backend", None)
    return backend is not None and backend != "bridge"


def _byok_llm(user_key: str, base_url: str = "", model: str = ""):
    """A per-request LLM backend using the caller's own key — against this deployment's configured
    provider/model by default (e.g. their own Gemini key when CHAVRUTA_LLM_PRESET=gemini), or against
    a DIFFERENT provider/model if the caller named one (validated first via /byok/check — see its
    docstring for why guessing a model on an unfamiliar provider is never done here). Used for
    exactly one request and then discarded; nothing about it is written to disk."""
    pipeline = _get_pipeline()
    profile = pipeline.profile
    from chavruta.llm.cloud import CloudLLM

    # min_output_tokens (the floor against a reasoning model burning its whole budget on <think>) is a
    # property of the SPECIFIC model this deployment was tuned for — it does not transfer to a model
    # the caller picked on their own. Applying it there could as easily be wrong as right, so a custom
    # model gets no floor rather than a guessed one; a caller picking a reasoning model elsewhere
    # accepts that risk themselves (it is exactly what /byok/check's cost/support disclaimer covers).
    custom_model = model.strip()
    llm = CloudLLM(custom_model or profile.llm_model, base_url.strip() or profile.llm_base_url,
                   user_key, timeout_s=profile.llm_timeout_s, max_retries=profile.llm_max_retries,
                   min_output_tokens=0 if custom_model else getattr(profile, "llm_min_output_tokens", 0))
    pipeline.wire_source_fetcher(llm)
    return llm


class ByokCheckRequest(BaseModel):
    model: str = Field(max_length=200)
    base_url: str = Field(default="", max_length=300)   # "" ⇒ this deployment's own configured provider


class ByokCheckOut(BaseModel):
    ok: bool
    models: list[str] = []   # populated only when ok is False and the provider could be reached
    message: str = ""        # localized-enough plain text explaining the result either way


# A caller entering a custom provider/model in Settings validates it here BEFORE it is ever wired
# into a real generation call — not mid-conversation. Rationale: guessing a model name across an
# unfamiliar provider is unsafe (see _byok_llm), so the model is checked against that provider's own
# /models listing once at setup time, and the mismatch path hands back the real list to pick from.
@app.post("/byok/check", response_model=ByokCheckOut)
def byok_check(req: ByokCheckRequest, lang: str = "he", owner: str = Depends(current_owner),
              x_user_llm_key: str | None = Header(default=None, alias="X-User-LLM-Key")):
    he = (lang or "he").startswith("he")
    key = _hstr(x_user_llm_key)
    if not key:
        raise HTTPException(status_code=422, detail="missing X-User-LLM-Key")
    if not _byok_supported():
        raise HTTPException(status_code=400,
                            detail="this deployment's backend has no provider-key concept (bridge)")
    base_url = req.base_url.strip() or _get_pipeline().profile.llm_base_url
    model = req.model.strip()

    from chavruta.llm.cloud import list_models
    try:
        models = list_models(base_url, key)
    except Exception as exc:
        # Cannot reach the provider to validate at all (bad key, bad URL, network) — say so plainly
        # rather than silently letting a broken key/URL combination through to a real generation call.
        _log.info("byok_check: could not list models at %s: %s", base_url, exc)
        return ByokCheckOut(
            ok=False,
            message=("לא הצלחנו להתחבר לספק כדי לאמת את המפתח/הכתובת — בדוק שהמפתח וכתובת ה-Base "
                     "URL נכונים.") if he else
                    "Could not reach the provider to validate the key/URL — check that both are correct.")
    if model in models:
        return ByokCheckOut(ok=True)
    return ByokCheckOut(
        ok=False, models=models,
        message=("המודל הזה לא נמצא אצל הספק הזה — בחר אחד מהרשימה. שים לב: אין לנו דרך לדעת את "
                 "העלות של כל מודל (ה-API של הספק לא חושף מחירים) — האחריות לבדוק את המחיר מול "
                 "הספק היא שלך, ואיננו נושאים באחריות לעלויות שייווצרו.") if he else
                "This model was not found at this provider — pick one from the list. Note: we have "
                "no way to know each model's cost (the provider's API does not expose pricing) — "
                "checking the price with the provider is your responsibility, and we take no "
                "responsibility for costs incurred.")


# ── Daily quota, per subscription plan ────────────────────────────────────────
def _quota_message(kind: str, lang: str, balance: int, cost: int) -> str:
    """The 429 body. States WHEN the allowance returns — "come back tomorrow" is wrong and
    infuriating when it is the week that is spent — and never prints an absolute allowance, so a
    budget change is not a broken promise to a paying customer."""
    he = (lang or "he").startswith("he")
    heads = {
        "lesson": ("הגעת למכסת השיעורים השבועית. היא מתאפסת ביום ראשון.",
                   "You've used this week's lessons. It resets on Sunday."),
        "week": ("הגעת למכסת השימוש השבועית. היא מתאפסת ביום ראשון.",
                 "You've reached this week's usage limit. It resets on Sunday."),
        "day": ("הגעת למכסת השימוש היומית. היא מתאפסת מחר.",
                "You've reached today's usage limit. It resets tomorrow."),
    }
    head = heads[kind][0 if he else 1]
    tail = (f" נותרו לך {balance} קרדיטים (הפעולה הזו עולה {cost}). "
            "אפשר לשדרג את התוכנית או להזין קוד קופון."
            if he else
            f" You have {balance} credits (this action costs {cost}). "
            "You can upgrade your plan or redeem a coupon.")
    return head + tail


def _enforce_lesson_quota(owner: str, lang: str, user_key: str = "") -> bool:
    """The lesson pool: a weekly COUNT, entirely independent of conversation tokens. Returns whether
    the turn was admitted via the BYOK fallback (see module docstring above) rather than the plan's
    own quota — the caller uses this to decide which backend/meter the turn actually runs against.

    A lesson is a discrete thing a teacher plans around, so it is counted, not metered. Running out
    of conversation tokens must NOT block a lesson, and a lesson must not spend them — the whole
    point of keeping the two pools apart. Cost stays bounded by (lessons per week x the per-lesson
    token budget the pipeline already enforces).
    """
    limit = plans.weekly_lessons(db.get_plan(owner))
    if limit <= 0:
        return False
    allowed, _d, _w = db.bump_usage(owner, 0, weekly_limit=limit, units=1, meter=db.LESSON)
    if allowed:
        return False
    if user_key and _byok_supported():
        b_allowed, _bd, _bw = db.bump_usage(owner, 0, weekly_limit=limit, units=1, meter=db.BYOK_LESSON)
        if b_allowed:
            return True
    cost = plans.credit_cost("lesson")
    spent, balance = db.spend_credits(owner, cost)
    if spent:
        _log.info("owner=%s over weekly lesson quota; spent %d credit(s), %d left", owner, cost, balance)
        return False
    raise HTTPException(status_code=429, detail=_quota_message("lesson", lang, balance, cost))


def _reserve_tokens(owner: str, lang: str, intent: str, user_key: str = "") -> tuple[int, bool]:
    """Admit a conversation turn against an ESTIMATE of its token cost. Returns (reserved, used_byok).

    The quota is denominated in tokens but they are only known after the call, so the turn is
    charged an estimate up front and corrected by _settle_tokens once the real figure comes back.
    Without the reservation an account with almost nothing left could still launch the largest
    request in the system, and we would pay for it.

    When the plan's own allowance is exhausted and the caller supplied their own provider key
    (user_key), a SECOND reservation of the same size is tried against the BYOK meter before falling
    back to credits — see the module docstring above _byok_supported.
    """
    estimate = plans.token_estimate(intent)
    plan = db.get_plan(owner)
    daily, weekly = plans.daily_tokens(plan), plans.weekly_tokens(plan)
    if daily <= 0 and weekly <= 0:
        return 0, False

    allowed, _d, used_week = db.bump_usage(owner, daily, weekly_limit=weekly, units=estimate,
                                           meter=db.TOKENS)
    if allowed:
        return estimate, False

    weekly_hit = weekly > 0 and used_week + estimate > weekly

    if user_key and _byok_supported():
        b_allowed, _bd, _bw = db.bump_usage(owner, daily, weekly_limit=weekly, units=estimate,
                                            meter=db.BYOK_TOKENS)
        if b_allowed:
            return estimate, True

    cost = plans.credit_cost(intent)
    spent, balance = db.spend_credits(owner, cost)
    if spent:
        _log.info("owner=%s over %s token quota; spent %d credit(s), %d left",
                  owner, "weekly" if weekly_hit else "daily", cost, balance)
        return 0, False            # paid for with credits — nothing reserved, so nothing to settle
    raise HTTPException(status_code=429,
                        detail=_quota_message("week" if weekly_hit else "day", lang, balance, cost))


def _settle_tokens(owner: str, reserved: int, usage: dict, intent: str, meter: str = db.TOKENS) -> None:
    """Replace the reservation with what the request actually spent, against whichever meter it was
    reserved from (the plan's own TOKENS, or BYOK_TOKENS when the turn ran on the caller's own key).

    Lessons are skipped entirely: they are metered as a weekly count in their own pool, so charging
    their (large) token spend to the conversation pool would silently couple the two — the exact
    thing keeping them separate is for.
    """
    if owner == "local" or plans.is_lesson(intent):
        return
    actual = plans.normalized_tokens(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
    if not actual and not reserved:
        return
    total = db.settle_usage(owner, reserved, actual, meter=meter)
    _log.info("owner=%s meter=%s tokens reserved=%d actual=%d calls=%d total=%d",
              owner, meter, reserved, actual, usage.get("calls", 0), total)


def _metered(owner: str, reserved: int, intent: str, fn, req: QueryRequest | None = None,
            meter: str = db.TOKENS):
    """Wrap a generation so its real token spend replaces the reservation, and record what happened.

    Returns a callable rather than running immediately because the async endpoints hand this to the
    job queue: the meter uses a ContextVar, and a worker thread starts with an empty context, so it
    has to be opened INSIDE the job — not around the submit call, where it would collect nothing.

    Settlement runs in a finally block: a failed generation still burned whatever tokens it burned
    before failing, and leaving the reservation standing would over-charge instead. `meter` picks
    which pool the settlement lands in (see _settle_tokens) — TOKENS normally, BYOK_TOKENS when the
    turn was admitted on the caller's own key.
    """
    def run():
        t0 = time.monotonic()
        result = error = None
        with metering.meter() as usage:
            try:
                result = fn()
                return result
            except Exception as exc:
                error = type(exc).__name__
                raise
            finally:
                _settle_tokens(owner, reserved, usage, intent, meter=meter)
                _record_event(owner, intent, req, usage, result, error,
                              ms=int((time.monotonic() - t0) * 1000))
    return run


# Telemetry is written in Israel local time for the hour-of-day view: "when do teachers prepare?" is
# a question about their evening, not about UTC.
_LOCAL_TZ = ZoneInfo(os.environ.get("CHAVRUTA_TZ", "Asia/Jerusalem"))


def _record_event(owner: str, intent: str, req: QueryRequest | None, usage: dict,
                  result, error: str | None, *, ms: int) -> None:
    """Append one generation's measurements. Measurements only — no question, answer, source or
    attachment text ever reaches this table (see the schema comment)."""
    try:
        now = datetime.now(UTC)
        local = now.astimezone(_LOCAL_TZ)
        payload = result if isinstance(result, dict) else None
        got = payload if payload is not None else (result.model_dump() if result is not None else {})
        db.record_usage_event(
            at=now.isoformat(),
            hour_local=local.hour,
            dow=(local.weekday() + 1) % 7,          # 0 = Sunday, the week this product works in
            owner_id=None if owner == "local" else owner,
            plan=None if owner == "local" else plans.canonical(db.get_plan(owner)),
            intent=(got.get("intent") or intent or "qa"),
            lang=(req.lang if req else "") or "he",
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            billed_tokens=plans.normalized_tokens(usage.get("prompt_tokens", 0),
                                                  usage.get("completion_tokens", 0)),
            llm_calls=usage.get("calls", 0),
            ms=ms,
            concurrent_at_start=_concurrency_at_start.get(),
            grounded=int(bool(got.get("grounded"))) if got else None,
            no_source=int(not got.get("citations")) if got else None,
            citations=len(got.get("citations") or []),
            audience=(req.audience or None) if req else None,
            grade_band=(req.grade_band or None) if req else None,
            length=(req.length or None) if req else None,
            attachments=len(req.attachments) if req else 0,
            error=error,
        )
    except Exception:                       # noqa: BLE001 — analytics must never break a request
        _log.exception("failed to record usage telemetry")


def _enforce_quota(owner: str, lang: str, intent: str = "", user_key: str = "") -> tuple[int, bool]:
    """Route a request to its pool and admit it. Returns (tokens reserved (0 for a lesson), used_byok).

    Only bites authenticated users (owner != 'local'); local/offline use is uncapped. Enforced
    before ownership checks so an over-quota user probing session ids learns nothing. `user_key` is
    the caller's own provider API key (X-User-LLM-Key), if any — see _byok_supported.
    """
    if owner == "local":
        return 0, False
    if plans.is_lesson(intent):
        return 0, _enforce_lesson_quota(owner, lang, user_key)
    return _reserve_tokens(owner, lang, intent, user_key)


def _hstr(v) -> str:
    """A Header()-dependency value as a plain, stripped string — '' for anything that isn't actually
    a string. FastAPI resolves these to a real str (or None) on a real request; a handful of existing
    unit tests call route functions directly as plain Python calls, which leaves the parameter holding
    the Header(...) marker object itself. Treated the same as "not supplied" rather than raising."""
    return v.strip() if isinstance(v, str) else ""


def _resolve_llm_for_request(owner: str, lang: str, intent: str, user_key: str | None,
                             base_url: str | None = None, model: str | None = None):
    """One-stop call for every route below: enforce quota (with the BYOK fallback), and return
    (reserved, llm_override, meter) — llm_override is None (use the pipeline's own shared backend)
    unless the turn was actually admitted on the caller's own key, in which case it's a fresh
    single-request CloudLLM built from it (see _byok_llm) and meter is BYOK_TOKENS so settlement
    lands in the right pool. `base_url`/`model` let the caller point their key at a different
    provider/model entirely — see _byok_llm's docstring."""
    key = _hstr(user_key)
    reserved, used_byok = _enforce_quota(owner, lang, intent, user_key=key)
    if used_byok:
        return reserved, _byok_llm(key, _hstr(base_url), _hstr(model)), db.BYOK_TOKENS
    return reserved, None, db.TOKENS


class QueryRequest(BaseModel):
    # Bounded so a giant body can't blow up the bridge job files / prompt tokens (a 422 is returned
    # for over-length input). 8k chars is far beyond any real question incl. a pasted source.
    question: str = Field(max_length=8000)
    lang: str = Field(default="", max_length=8)
    intent: str = Field(default="", max_length=32)
    audience: str = ""       # lesson mode: "" (auto) | "yeshiva" | "school"
    grade_band: str = ""     # school lessons: a-c | d-f | g-i | j-l
    length: str = ""         # "" (medium) | "short" | "medium" | "long"
    attachments: list[Attachment] = []   # user-brought sources (text / pdf / word); images pending OCR


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest, owner: str = Depends(current_owner),
         x_user_llm_key: str | None = Header(default=None, alias="X-User-LLM-Key"),
         x_user_llm_base_url: str | None = Header(default=None, alias="X-User-LLM-Base-URL"),
         x_user_llm_model: str | None = Header(default=None, alias="X-User-LLM-Model")):
    if not req.question.strip():
        raise HTTPException(status_code=422, detail="question must not be empty")
    reserved, llm, meter = _resolve_llm_for_request(owner, req.lang, req.intent, x_user_llm_key)
    return _metered(owner, reserved, req.intent, lambda: _run_query(
        _augment_question(req.question, req.attachments), req.lang, req.intent, [],
        audience=req.audience, grade_band=req.grade_band, length=req.length, owner_id=owner, llm=llm),
        req, meter=meter)()


class MeOut(BaseModel):
    owner: str
    authenticated: bool
    plan: str = "free"               # tier id — see app/plans.py
    plan_name: str = ""              # localized display name for the UI
    # Allowances are reported as FRACTIONS REMAINING (1.0 = untouched, 0.0 = spent), never as
    # absolute tokens or lessons. A published number becomes a promise, and a token figure means
    # nothing to a reader anyway; a gauge and a tier multiple say everything a user needs.
    day_left: float | None = None      # conversation pool, today. None ⇒ uncapped
    week_left: float | None = None     # conversation pool, this week
    lessons_left: float | None = None  # lesson pool, this week (its own pool)
    lessons_exhausted: bool = False    # so the UI can grey out lesson mode specifically
    multiple: int = 1                  # this tier's usage relative to free — the only figure shown
    # BYOK (bring-your-own-key): whether this deployment's backend even has a provider-key concept
    # (false for 'bridge'), and — if the caller supplies their own key — a SECOND allowance the same
    # size as their plan's, spent only once the plan's own pool above is exhausted. See
    # app/api.py::_byok_supported / _resolve_llm_for_request.
    byok_supported: bool = False
    byok_day_left: float | None = None
    byok_week_left: float | None = None
    byok_lessons_left: float | None = None
    credits: int = 0                   # prepaid generations, spent once a cap is hit
    plan_until: str | None = None    # ISO ts the paid/coupon period ends
    cycle: str = "monthly"           # 'monthly' | 'annual' | 'coupon'
    cancel_at_period_end: bool = False   # true ⇒ cancelled, access runs to plan_until then lapses
    deletion_scheduled_for: str | None = None   # ISO ts if the account is pending deletion
    blocked: bool = False            # account on the blocklist
    blocked_until: str | None = None  # ISO ts the block lifts (None + blocked ⇒ permanent)
    blocked_reason: str = ""


@app.get("/me", response_model=MeOut)
def me(owner: str = Depends(current_owner)):
    """Account + today's quota state — lets the UI show who's signed in, their plan, how many questions
    remain, whether a deletion is pending, and whether the account is blocked."""
    plan = "free" if owner == "local" else plans.canonical(db.get_plan(owner))
    is_local = owner == "local"
    ban = None if is_local else accounts.active_ban(owner)
    sub = (None if is_local else db.get_subscription(owner)) or {}

    def _left(used: int, cap: int) -> float | None:
        """Fraction of an allowance still available, rounded to whole percent — fine enough for a
        gauge, coarse enough that nobody can reverse-engineer the cap by watching it move."""
        if is_local or cap <= 0:
            return None
        return round(max(0.0, min(1.0, (cap - used) / cap)), 2)

    day_left = _left(0 if is_local else db.usage_today(owner, meter=db.TOKENS),
                     plans.daily_tokens(plan))
    week_left = _left(0 if is_local else db.usage_this_week(owner, meter=db.TOKENS),
                      plans.weekly_tokens(plan))
    lessons_left = _left(0 if is_local else db.usage_this_week(owner, meter=db.LESSON),
                         plans.weekly_lessons(plan))
    byok_day_left = _left(0 if is_local else db.usage_today(owner, meter=db.BYOK_TOKENS),
                         plans.daily_tokens(plan))
    byok_week_left = _left(0 if is_local else db.usage_this_week(owner, meter=db.BYOK_TOKENS),
                          plans.weekly_tokens(plan))
    byok_lessons_left = _left(0 if is_local else db.usage_this_week(owner, meter=db.BYOK_LESSON),
                             plans.weekly_lessons(plan))
    return MeOut(
        owner=owner,
        authenticated=not is_local,
        plan=plan,
        plan_name=plans.tier(plan).name_he,
        day_left=day_left,
        week_left=week_left,
        lessons_left=lessons_left,
        lessons_exhausted=lessons_left == 0.0,
        multiple=plans.tier(plan).multiple,
        byok_supported=_byok_supported(),
        byok_day_left=byok_day_left,
        byok_week_left=byok_week_left,
        byok_lessons_left=byok_lessons_left,
        credits=0 if is_local else db.get_credits(owner),
        plan_until=sub.get("current_period_end") if plan != "free" else None,
        cycle=sub.get("cycle") or "monthly",
        cancel_at_period_end=bool(sub.get("cancel_at_period_end")),
        deletion_scheduled_for=None if owner == "local" else accounts.scheduled_for(owner),
        blocked=ban is not None,
        blocked_until=ban["until"] if ban else None,
        blocked_reason=ban["reason"] if ban else "",
    )


# ── Account deletion (scheduled, with a grace period + cancel) ────────────────
class DeletionOut(BaseModel):
    deletion_scheduled_for: str | None = None


@app.post("/account/delete", response_model=DeletionOut)
def request_account_deletion(owner: str = Depends(current_owner)):
    """Schedule this account for deletion after a grace period. The user can cancel until then; at the
    deadline the background sweeper purges all their data (and the Supabase login, if configured)."""
    if owner == "local":
        # No account to delete in local/offline mode (the single-user store isn't an account).
        raise HTTPException(status_code=400, detail="no account in local mode")
    return DeletionOut(deletion_scheduled_for=accounts.schedule(owner))


@app.post("/account/delete/cancel", response_model=DeletionOut)
def cancel_account_deletion(owner: str = Depends(current_owner)):
    """Cancel a pending deletion — the account stays active."""
    if owner != "local":
        accounts.cancel(owner)
    return DeletionOut(deletion_scheduled_for=None)


# ── Billing (subscription checkout / cancel / webhook) ────────────────────────
class CheckoutRequest(BaseModel):
    email: str = ""
    name: str = ""
    plan: str = "pro"                        # tier id — see app/plans.py
    cycle: str = "monthly"                   # 'monthly' | 'annual' (a prepaid, discounted year)


class CheckoutOut(BaseModel):
    url: str


@app.get("/billing/config")
def billing_config(lang: str = "he"):
    """Whether billing is available (so the UI can show/hide the upgrade button), plus the tier
    catalogue so prices are never hardcoded in the frontend."""
    return {"enabled": billing.enabled(), "tiers": plans.public_catalogue(lang)}


@app.get("/billing/limits")
def billing_limits(lang: str = "he"):
    """The absolute usage limits for each tier — for the /limits page.

    This is a public, unauthenticated endpoint because the figures must be readable before buying.
    The marketing UI shows only a ratio ("3x the usage"); this endpoint provides the absolute
    numbers (daily_tokens, weekly_tokens, weekly_lessons) that a customer needs to know what they
    are actually purchasing. See plans.limits_catalogue() for the rationale.
    """
    return {"tiers": plans.limits_catalogue(lang)}


# ── Coupons ───────────────────────────────────────────────────────────────────
class RedeemRequest(BaseModel):
    code: str = Field(max_length=64)


class RedeemOut(BaseModel):
    ok: bool = True
    kind: str = ""                   # 'plan' | 'credits'
    plan: str | None = None
    plan_name: str = ""
    until: str | None = None         # ISO ts a plan grant/boost lapses
    credits_added: int = 0
    credits_balance: int = 0
    message: str = ""
    discount_added_ils: float = 0    # >0 only for mode="discount" (coupon rebated off future charges)


# Stable reason → user-facing message. "invalid" deliberately covers not-found, revoked and
# malformed alike: telling a prober which of those it hit turns the endpoint into an oracle for
# discovering real codes.
_REDEEM_MESSAGES = {
    "sign_in_required": ("צריך להתחבר כדי לממש קוד.", "Sign in to redeem a code."),
    "invalid": ("הקוד אינו תקף.", "That code isn't valid."),
    "already_redeemed": ("כבר מימשת את הקוד הזה.", "You've already redeemed this code."),
    "exhausted": ("הקוד מוצה — כל המימושים נוצלו.", "This code has been fully redeemed."),
    "expired": ("תוקף הקוד פג.", "This code has expired."),
    "throttled": ("יותר מדי ניסיונות. נסה שוב בעוד שעה.", "Too many attempts. Try again in an hour."),
    "downgrade": ("הקוד נותן רמה נמוכה מזו שיש לך כבר.",
                  "That code grants a lower tier than you already have."),
}
_REDEEM_STATUS = {"throttled": 429, "sign_in_required": 401}


@app.post("/coupons/redeem", response_model=RedeemOut)
def redeem_coupon(req: RedeemRequest, lang: str = "he", owner: str = Depends(current_owner)):
    """Redeem a coupon code for a time-boxed plan or a pile of credits."""
    he = (lang or "he").startswith("he")
    try:
        res = coupons.redeem(owner, req.code)
    except coupons.RedeemError as exc:
        msg = _REDEEM_MESSAGES.get(exc.reason, _REDEEM_MESSAGES["invalid"])
        raise HTTPException(status_code=_REDEEM_STATUS.get(exc.reason, 400),
                            detail=msg[0] if he else msg[1]) from exc

    if res["kind"] == "credits":
        message = (f"נוספו {res['credits_added']} קרדיטים. יתרה: {res['credits_balance']}."
                   if he else
                   f"{res['credits_added']} credits added. Balance: {res['credits_balance']}.")
    else:
        name = plans.tier(res["plan"]).name_he if he else plans.tier(res["plan"]).name_en
        until = (res["until"] or "")[:10]
        mode = res.get("mode", "grant")
        if mode == "discount":
            discount = res.get("discount_added_ils", 0)
            message = (f"קיבלת הנחה של ₪{discount:.2f} על החיובים הבאים." if he else
                       f"You got a ₪{discount:.2f} discount on upcoming charges.")
        elif mode == "boost":
            message = (f"שודרגת זמנית ל'{name}' עד {until}." if he else
                       f"Temporarily upgraded to {name} until {until}.")
        else:
            message = (f"התוכנית שודרגה ל'{name}' עד {until}." if he else
                       f"Upgraded to {name} until {until}.")
    return RedeemOut(kind=res["kind"], plan=res["plan"],
                     plan_name=plans.tier(res["plan"]).name_he if res["plan"] else "",
                     until=res["until"], credits_added=res["credits_added"],
                     credits_balance=res["credits_balance"], message=message,
                     discount_added_ils=res.get("discount_added_ils", 0))


@app.post("/billing/checkout", response_model=CheckoutOut)
def billing_checkout(req: CheckoutRequest, owner: str = Depends(current_owner)):
    """Create a hosted payment page and return its URL. The client redirects the user there."""
    if owner == "local":
        raise HTTPException(status_code=400, detail="sign in to subscribe")
    if not billing.enabled():
        raise HTTPException(status_code=503, detail="billing not configured")
    try:
        return CheckoutOut(url=billing.start_checkout(owner, req.email, req.name,
                                                      plan=req.plan, cycle=req.cycle))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:            # noqa: BLE001 — surface a clean 502 rather than a stack trace
        _log.exception("checkout failed for %s", owner)
        raise HTTPException(status_code=502, detail="could not start checkout") from exc


@app.post("/billing/cancel")
def billing_cancel(owner: str = Depends(current_owner)):
    """Cancel the subscription — stops future charges; paid access lasts until the period end."""
    if owner == "local":
        raise HTTPException(status_code=400, detail="no subscription in local mode")
    billing.cancel(owner)
    return {"ok": True}


@app.post("/billing/webhook")
async def billing_webhook(request: Request):
    """PayPlus charge callback. Public (no bearer — PayPlus can't send one) but authenticated by the
    HMAC `hash` header over the raw body; unverified posts are rejected. Exempt from the auth gate."""
    # Closed while billing is unconfigured: there is no secret to verify against, so nothing posted
    # here could be authentic. (verify_webhook fails closed too — this just answers honestly.)
    if not billing.enabled():
        raise HTTPException(status_code=503, detail="billing not configured")
    raw = await request.body()
    if not payplus.verify_webhook(raw, request.headers.get("user-agent"), request.headers.get("hash")):
        raise HTTPException(status_code=400, detail="invalid signature")
    import json
    try:
        payload = json.loads(raw or b"{}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="bad payload") from exc
    billing.handle_event(payplus.parse_event(payload))
    return {"ok": True}


# ── Sessions ──────────────────────────────────────────────────────────────────

class SessionOut(BaseModel):
    id: str
    first_q: str
    created_at: str
    updated_at: str | None = None
    mode: str | None = None          # the chat's locked mode (intent from its first turn)


class SessionCreateOut(SessionOut):
    # The first-query result must survive serialization — a bare SessionOut
    # response_model would strip it (client then sees no `result`/`answer`).
    result: QueryResponse


@app.get("/sessions", response_model=list[SessionOut])
def list_sessions(owner: str = Depends(current_owner)):
    return db.list_sessions(owner)


class SessionQueryResponse(QueryResponse):   # inherits lesson_plan etc.
    session_id: str


class JobAccepted(BaseModel):
    """202 body for the async endpoints: a job id to poll, plus the session id when one was just
    created so the client can attach the chat to the UI before generation finishes."""
    job_id: str
    session_id: str | None = None


def _save_assistant(session_id: str, result: QueryResponse) -> None:
    """Persist a generated answer as the assistant turn — the one place that maps a QueryResponse
    onto the message columns, shared by every (sync/async, create/continue) path."""
    message_id = db.save_message(
        session_id,
        "assistant",
        result.answer,
        intent=result.intent,
        citations=[c.model_dump() for c in result.citations],
        caveats=result.caveats,
        grounded=result.grounded,
        files=[f.model_dump() for f in result.files],
    )
    # Point the library entry at the turn that now holds the same documents, so deleting the lesson
    # can clear both copies. Best-effort: a lesson that stays unlinked still deletes from the
    # library, it just leaves the chat copy — worth a log line, not a failed request.
    if result.lesson_id:
        try:
            db.link_lesson_message(result.lesson_id, message_id)
        except Exception:
            _log.warning("could not link lesson %s to message %s", result.lesson_id, message_id)


def _first_query_work(sid: str, req: QueryRequest, owner: str, llm=None) -> dict:
    """Run the first query for an already-created session, save the assistant turn, and return the
    SessionCreateOut-shaped payload. Runs identically inline (sync route) or inside a job (async).

    _run_query degrades ordinary retrieval/LLM failures to an error answer (so a turn is still saved),
    but it re-raises real 4xx (e.g. an unrecognised intent). If that happens the session would be left
    with a user turn and no answer — a blank chat stuck in the list — so we delete it on failure."""
    try:
        result = _run_query(_augment_question(req.question, req.attachments), req.lang, req.intent, [],
                            audience=req.audience, grade_band=req.grade_band, length=req.length,
                            owner_id=owner, llm=llm)
    except Exception:
        db.delete_session(sid, owner)   # don't leave a half-created, answer-less session behind
        raise
    _save_assistant(sid, result)
    row = next(s for s in db.list_sessions(owner) if s["id"] == sid)
    return {"id": sid, "first_q": row["first_q"], "created_at": row["created_at"], "result": result}


def _prepare_continue(session_id: str, req: QueryRequest, owner: str) -> tuple[list[Turn], str]:
    """Shared setup for continuing a session: ownership gate (404 if not owned), build the trailing
    history, save the user turn, and resolve the sticky/locked intent. Returns (history, intent)."""
    history_rows = db.get_messages(session_id, owner)
    if not history_rows:
        # A session the caller doesn't own reads as not-found — no history leak, no writing into
        # someone else's chat.
        raise HTTPException(status_code=404, detail="session not found")
    history = [Turn(role=m["role"], text=m["text"]) for m in history_rows[-8:]]
    db.save_message(session_id, "user", req.question)
    # Sticky mode: a chat stays in the mode chosen on its first turn — ignore any intent the client
    # sends on later turns. Legacy sessions (mode=NULL) fall back to the per-request intent.
    locked_mode = db.get_session_mode(session_id, owner)
    return history, (locked_mode or req.intent)


def _continue_query_work(session_id: str, req: QueryRequest, history: list[Turn], intent: str,
                         owner: str, llm=None) -> SessionQueryResponse:
    """Run a follow-up turn, save the assistant answer, and return the SessionQueryResponse."""
    result = _run_query(_augment_question(req.question, req.attachments), req.lang, intent, history,
                        audience=req.audience, grade_band=req.grade_band, length=req.length,
                        owner_id=owner, llm=llm)
    _save_assistant(session_id, result)
    return SessionQueryResponse(**result.model_dump(), session_id=session_id)


@app.post("/sessions", response_model=SessionCreateOut, status_code=201)
def create_session(req: QueryRequest, owner: str = Depends(current_owner),
                   x_user_llm_key: str | None = Header(default=None, alias="X-User-LLM-Key"),
                   x_user_llm_base_url: str | None = Header(default=None, alias="X-User-LLM-Base-URL"),
                   x_user_llm_model: str | None = Header(default=None, alias="X-User-LLM-Model")):
    """Create a new session and run the first query (synchronous — fine for quick Q&A; use
    /sessions/async for a long lesson that would outlast a proxy timeout)."""
    if not req.question.strip():
        raise HTTPException(status_code=422, detail="question must not be empty")
    reserved, llm, meter = _resolve_llm_for_request(owner, req.lang, req.intent, x_user_llm_key,
                                                    x_user_llm_base_url, x_user_llm_model)

    # Lock the chat's mode to the intent chosen on this first turn; every follow-up stays in it.
    sid = db.create_session(req.question.strip(), mode=req.intent or None, owner_id=owner)
    db.save_message(sid, "user", req.question)
    return _metered(owner, reserved, req.intent,
                    lambda: _first_query_work(sid, req, owner, llm=llm), req, meter=meter)()


@app.post("/sessions/{session_id}/query", response_model=SessionQueryResponse)
def session_query(session_id: str, req: QueryRequest, owner: str = Depends(current_owner),
                  x_user_llm_key: str | None = Header(default=None, alias="X-User-LLM-Key"),
                  x_user_llm_base_url: str | None = Header(default=None, alias="X-User-LLM-Base-URL"),
                  x_user_llm_model: str | None = Header(default=None, alias="X-User-LLM-Model")):
    """Continue an existing session (synchronous)."""
    if not req.question.strip():
        raise HTTPException(status_code=422, detail="question must not be empty")
    reserved, llm, meter = _resolve_llm_for_request(owner, req.lang, req.intent, x_user_llm_key,
                                                    x_user_llm_base_url, x_user_llm_model)
    history, intent = _prepare_continue(session_id, req, owner)
    return _metered(owner, reserved, req.intent,
                    lambda: _continue_query_work(session_id, req, history, intent, owner, llm=llm),
                    req, meter=meter)()


# ── Async generation (job queue) ──────────────────────────────────────────────
# A full lesson can take minutes — longer than a proxy's 504 window. These mirror the sync endpoints
# but return a job id immediately (202); the client polls GET /jobs/{id}. See app/jobs.py.

@app.post("/query/async", response_model=JobAccepted, status_code=202)
def query_async(req: QueryRequest, owner: str = Depends(current_owner),
                x_user_llm_key: str | None = Header(default=None, alias="X-User-LLM-Key"),
                x_user_llm_base_url: str | None = Header(default=None, alias="X-User-LLM-Base-URL"),
                x_user_llm_model: str | None = Header(default=None, alias="X-User-LLM-Model")):
    if not req.question.strip():
        raise HTTPException(status_code=422, detail="question must not be empty")
    reserved, llm, meter = _resolve_llm_for_request(owner, req.lang, req.intent, x_user_llm_key,
                                                    x_user_llm_base_url, x_user_llm_model)
    q = _augment_question(req.question, req.attachments)
    jid = jobs.submit(owner, _metered(owner, reserved, req.intent, lambda: jsonable_encoder(
        _run_query(q, req.lang, req.intent, [], audience=req.audience,
                   grade_band=req.grade_band, length=req.length, owner_id=owner, llm=llm)),
        req, meter=meter))
    return JobAccepted(job_id=jid)


@app.post("/sessions/async", response_model=JobAccepted, status_code=202)
def create_session_async(req: QueryRequest, owner: str = Depends(current_owner),
                         x_user_llm_key: str | None = Header(default=None, alias="X-User-LLM-Key"),
                         x_user_llm_base_url: str | None = Header(default=None, alias="X-User-LLM-Base-URL"),
                         x_user_llm_model: str | None = Header(default=None, alias="X-User-LLM-Model")):
    """Create the session synchronously (so the client gets session_id at once) and run the first
    query in the background."""
    if not req.question.strip():
        raise HTTPException(status_code=422, detail="question must not be empty")
    reserved, llm, meter = _resolve_llm_for_request(owner, req.lang, req.intent, x_user_llm_key,
                                                    x_user_llm_base_url, x_user_llm_model)
    sid = db.create_session(req.question.strip(), mode=req.intent or None, owner_id=owner)
    db.save_message(sid, "user", req.question)
    jid = jobs.submit(owner, _metered(
        owner, reserved, req.intent,
        lambda: jsonable_encoder(_first_query_work(sid, req, owner, llm=llm)),
        req, meter=meter))
    return JobAccepted(job_id=jid, session_id=sid)


@app.post("/sessions/{session_id}/query/async", response_model=JobAccepted, status_code=202)
def session_query_async(session_id: str, req: QueryRequest, owner: str = Depends(current_owner),
                        x_user_llm_key: str | None = Header(default=None, alias="X-User-LLM-Key"),
                        x_user_llm_base_url: str | None = Header(default=None, alias="X-User-LLM-Base-URL"),
                        x_user_llm_model: str | None = Header(default=None, alias="X-User-LLM-Model")):
    if not req.question.strip():
        raise HTTPException(status_code=422, detail="question must not be empty")
    reserved, llm, meter = _resolve_llm_for_request(owner, req.lang, req.intent, x_user_llm_key,
                                                    x_user_llm_base_url, x_user_llm_model)
    # The ownership gate + user-turn save happen NOW (before returning) so an unauthorized caller
    # gets a synchronous 404 and the user message is durable even if generation later fails.
    history, intent = _prepare_continue(session_id, req, owner)
    jid = jobs.submit(owner, _metered(owner, reserved, req.intent, lambda: jsonable_encoder(
        _continue_query_work(session_id, req, history, intent, owner, llm=llm)), req, meter=meter))
    return JobAccepted(job_id=jid, session_id=session_id)


class JobStatusOut(BaseModel):
    status: str                 # pending | running | done | error
    result: dict | None = None  # present when status == done (the endpoint's normal response body)
    error: str | None = None    # present when status == error


@app.get("/jobs/{job_id}", response_model=JobStatusOut)
def get_job(job_id: str, owner: str = Depends(current_owner)):
    """Poll an async generation job. Owner-scoped: another identity's job reads as not-found."""
    job = jobs.get(job_id, owner)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.status == "done":
        return JobStatusOut(status="done", result=job.result)
    if job.status == "error":
        return JobStatusOut(status="error", error=job.error)
    return JobStatusOut(status=job.status)


class MessageOut(BaseModel):
    id: int
    role: str
    text: str
    intent: str | None
    citations: list[dict]
    caveats: list[str]
    grounded: bool | None
    files: list[dict] = []
    created_at: str


@app.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
def get_messages(session_id: str, owner: str = Depends(current_owner)):
    msgs = db.get_messages(session_id, owner)
    if not msgs:
        raise HTTPException(status_code=404, detail="session not found")
    return msgs


@app.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str, owner: str = Depends(current_owner)):
    if not db.delete_session(session_id, owner):
        raise HTTPException(status_code=404, detail="session not found")


class ReportIn(BaseModel):
    reason: str = ""


# User-facing flag for a specific answer — the fast, low-cost mitigation for the residual defamation
# risk noted in docs/legal/LAWSUIT-EXPOSURE-2026-07-30.md Finding C: grounding in real sources reduces
# but does not eliminate the chance of a mischaracterizing answer about a real named person, so a
# quick report path (rather than none at all) is how one gets noticed and corrected.
@app.post("/messages/{message_id}/report", status_code=201)
def report_message(message_id: int, req: ReportIn, owner: str = Depends(current_owner)):
    try:
        db.report_message(message_id, owner, req.reason)
    except ValueError:
        raise HTTPException(status_code=404, detail="message not found")
    return {"ok": True}


# ── 'My Shiurim' lesson library ───────────────────────────────────────────────

class SavedLessonOut(BaseModel):
    id: str
    topic: str
    audience: str = ""
    grade_band: str = ""
    length: str = ""
    lang: str = "he"
    created_at: str


@app.get("/lessons", response_model=list[SavedLessonOut])
def list_lessons(owner: str = Depends(current_owner)):
    return db.list_lessons(owner)


@app.get("/lessons/{lesson_id}")
def get_lesson(lesson_id: str, owner: str = Depends(current_owner)):
    lesson = db.get_lesson(lesson_id, owner)
    if not lesson:
        raise HTTPException(status_code=404, detail="lesson not found")
    return lesson


@app.delete("/lessons/{lesson_id}", status_code=204)
def delete_lesson(lesson_id: str, owner: str = Depends(current_owner)):
    if not db.delete_lesson(lesson_id, owner):
        raise HTTPException(status_code=404, detail="lesson not found")
