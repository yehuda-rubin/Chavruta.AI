# -*- coding: utf-8 -*-
"""Chavruta.AI — Nebius Serverless Endpoint (FastAPI).

REST wrapper over ChavrutaPipeline for deployment as a Nebius Serverless Endpoint.
The pipeline is loaded once at startup and shared across requests.

    uvicorn app.api:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# Source markers ([S1], [S1, S5], (S1), 【S1】, …) are the grounding mechanism — the pipeline maps them
# to citations, then we strip them from the DISPLAYED text so the answer reads cleanly.
_MARKER_RE = re.compile(r"\s*[\[(（【]\s*S\d+(?:\s*,\s*S\d+)*\s*[\])）】]")


def _strip_markers(text: str) -> str:
    t = _MARKER_RE.sub("", text or "")
    t = re.sub(r"\*\*\s*\*\*", "", t)        # collapse empty **bold** left where a **[S#]** was stripped
    t = re.sub(r"(?<!\*)\*\s*\*(?!\*)", "", t)  # …and empty *italic*
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip()

import torch  # noqa: F401,E402 — MUST precede qdrant_client import (Windows pyarrow DLL order)

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from chavruta.config.profile import Profile
from chavruta.corpus.schema import Intent, Query, Turn

import app.db as db


# ── Startup ───────────────────────────────────────────────────────────────────

_pipeline = None


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        from chavruta.pipeline.pipeline import ChavrutaPipeline
        _pipeline = ChavrutaPipeline(Profile.from_env())
    return _pipeline


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.get_conn()          # initialise DB + run migrations
    p = _get_pipeline()    # warm up bge-m3 + Qdrant connection at startup
    try:
        p.embedding.embed_query("warmup")   # load the embedder BEFORE any qdrant_client use
    except Exception:
        pass
    yield


app = FastAPI(
    title="Chavruta.AI",
    description=(
        "Grounded Q&A, commentator explanation, and lesson preparation "
        "over the Jewish bookshelf (Tanakh + commentators). "
        "Every answer is cited to a retrieved source — nothing is invented."
    ),
    version="0.3.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:4173"],
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


# ── Lesson audience / grade / length ─────────────────────────────────────────
# The template RAG ('chavruta_templates', built by scripts/index_templates.py) is queried live
# to pick the right template SET for the topic — filtered by audience (yeshiva vs school) and,
# for school, by grade band — so the lesson is written at the correct register.

import os

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
    "short":  {"top_k": 10, "he": "קצר",  "yeshiva_min": "25–35 דק׳",
               "school_min": {"a-c": "15–20 דק׳", "d-f": "25–30 דק׳", "g-i": "25–30 דק׳", "j-l": "30–35 דק׳"},
               "depth": "שיעור קצר וממוקד: מעט מקורות, מהלך תמציתי ושיעור מלא קצר יחסית."},
    "medium": {"top_k": 16, "he": "בינוני", "yeshiva_min": "45–60 דק׳",
               "school_min": {"a-c": "30 דק׳", "d-f": "45 דק׳", "g-i": "45 דק׳", "j-l": "45–50 דק׳"},
               "depth": "שיעור באורך בינוני: כיסוי מאוזן של המקורות והמהלך."},
    "long":   {"top_k": 26, "he": "ארוך",  "yeshiva_min": "75–90 דק׳",
               "school_min": {"a-c": "40 דק׳ (בשני חלקים)", "d-f": "60–90 דק׳ (שיעור כפול)",
                              "g-i": "60–90 דק׳ (שיעור כפול)", "j-l": "90 דק׳ (שיעור כפול)"},
               "depth": "שיעור ארוך ומעמיק: מקורות רבים, מהלך מפורט ושיעור מלא ארוך ומעמיק."},
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
                pl[f"_{role}"] = (d / fn).read_text(encoding="utf-8")
            except Exception:
                pass


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
        r"|\bshort\b|\bmedium\b|\blong\b|\bbrief\b|\bschool\b|\byeshiva\w*|beit.?midrash|\bgrade\b|elementary"
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
              "התאם/י את הזמנים בשלבי מהלך השיעור כך שיסתכמו לטווח הזה.", ""]

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
                grade_band: str = "", length: str = "") -> QueryResponse:
    """Dedicated LESSON path: resolve audience/grade → pick a template from the template RAG →
    real source retrieval → Claude writes the 3 files at the right register (or asks clarifying
    questions first) via the bridge → 3 Word files + only-cited sources (in discussion order)."""
    pipeline = _get_pipeline()
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
    hits = list(pipeline.retriever.retrieve(rq, top_k=pool_k).hits)
    if not hits:
        msg = "לא נמצאו מקורות לנושא זה." if he else "No sources found for this topic."
        return QueryResponse(answer=msg, citations=[], grounded=False, intent="lesson", files=[])

    job = _lesson_job_md(topic, hits, lang, audience=aud, grade_band=band, length=length,
                         tpl=tpl, history=history)
    raw = pipeline.llm.request(job) if hasattr(pipeline.llm, "request") else ""

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
                                    deep_link=(getattr(h, "deep_link", "") or "")))
    ss, lf, fl = _strip_markers(ss), _strip_markers(lf), _strip_markers(fl)

    # Blank-file safety: if the model omitted/mis-split the SOURCE_SHEET, synthesize one from the cited
    # sources so the download is never blank.
    if not ss and used:
        ss = "\n\n".join(f"**{n}. {c.ref}**\n{c.text_he}" for n, c in enumerate(used, 1))

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
    # Citation-faithfulness: flag any verbatim quote in the lesson not found in the retrieved sources.
    from chavruta.generation.grounded import unverified_quotes
    bad_q = unverified_quotes(fl + "\n" + ss, hits)
    caveats = ([("הערה: ציטוטים בשיעור שלא אומתו מול המקורות — יש לבדוק: «" + "», «".join(bad_q[:2]) + "»")
                if he else ("Note: quote(s) in the lesson were not found in the sources — verify: «"
                            + "», «".join(bad_q[:2]) + "»")] if bad_q else [])
    # Persist to the 'My Shiurim' library so the teacher can reopen/reuse it later.
    if files:
        try:
            import uuid
            db.save_lesson(uuid.uuid4().hex[:12], topic, aud or "", band or "", length, lang,
                           [f.model_dump() for f in files], [c.model_dump() for c in used])
        except Exception:
            pass
    return QueryResponse(answer="", citations=used, grounded=bool(used) or bool(fl.strip()),
                         intent="lesson", caveats=caveats, files=files)


def _chavruta_job_md(question: str, hits, lang: str, history) -> str:
    """Bridge job: play a Socratic study-partner (chavruta) — learn WITH the user, don't lecture."""
    lines = [f"lang: {lang}", "", "## ROLE",
             "אתה **חברותא** לימודי — אתה לומד יחד עם המשתמש, בגובה העיניים, ולא מרצה מלמעלה.", ""]
    prior = [h for h in (history or []) if (getattr(h, "text", "") or "").strip()]
    if prior:
        lines += ["## CONVERSATION SO FAR"]
        for h in prior[-8:]:
            lines += [f"- {getattr(h, 'role', 'user')}: {(getattr(h, 'text', '') or '').strip()}"]
        lines += [""]
    lines += ["## THE LEARNER JUST SAID", question.strip(), "", "## SOURCES"]
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
        "Ground everything ONLY in the SOURCES; cite by [S#] (stripped from display). Keep it fairly short "
        "(a real chavruta exchange, not an essay). Write in the learner's language. **bold** key terms.",
    ]
    return "\n".join(lines)


def _run_chavruta(question: str, lang: str, history=None) -> QueryResponse:
    """Socratic study-partner mode: retrieve on the topic, then Claude plays a chavruta that asks
    questions and learns WITH the user (grounded), rather than lecturing."""
    pipeline = _get_pipeline()
    user_turns = [(getattr(h, "text", "") or "").strip() for h in (history or [])
                  if getattr(h, "role", "user") == "user" and (getattr(h, "text", "") or "").strip()]
    anchor = (user_turns[0] + " " + question) if user_turns else question   # keep retrieval on the topic
    q = Query(text=anchor, lang=lang or None, intent=Intent.QA)
    rq = pipeline._resolve_query(q)
    lang = rq.lang or lang or "he"
    hits = list(pipeline.retriever.retrieve(rq, top_k=10).hits)
    job = _chavruta_job_md(question, hits, lang, history)
    raw = pipeline.llm.request(job) if hasattr(pipeline.llm, "request") else ""
    nums, used, seen = [int(n) for n in re.findall(r"\[\s*S(\d+)\s*\]", raw)], [], set()
    for i in nums:
        if 1 <= i <= len(hits) and i not in seen:
            seen.add(i)
            h = hits[i - 1]
            used.append(CitationOut(ref=h.ref, text_he=(getattr(h, "text", "") or ""), text_en="",
                                    commentator=(getattr(h, "commentator_id", "") or ""),
                                    deep_link=(getattr(h, "deep_link", "") or "")))
    return QueryResponse(answer=_strip_markers(raw), citations=used, grounded=bool(used),
                         intent="chavruta", files=[])


def _run_query(question: str, lang: str, intent_str: str, history: list[Turn],
               audience: str = "", grade_band: str = "", length: str = "") -> QueryResponse:
    if intent_str == "shut":          # UI's responsa mode → HALACHA intent
        intent_str = "halacha"
    if intent_str == "chavruta":      # Socratic study-partner mode (its own path)
        return _run_chavruta(question, lang, history=history)
    intent = None
    if intent_str:
        try:
            intent = Intent(intent_str)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"unknown intent: {intent_str!r}")

    if intent == Intent.LESSON:            # lesson mode → Claude writes the 3 files, audience-adapted
        return _run_lesson(question, lang, history=history, audience=audience,
                           grade_band=grade_band, length=length)

    q = Query(text=question, lang=lang or None, intent=intent)
    answer = _get_pipeline().ask(q, history=history)

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

@app.get("/health")
def health():
    p = Profile.from_env()
    return {
        "status": "ok",
        "profile": p.name,
        "llm_backend": p.llm_backend,
        "llm_model": p.llm_model,
        "qdrant_mode": p.qdrant_mode,
    }


# ── Stateless query (backward-compatible) ────────────────────────────────────

class QueryRequest(BaseModel):
    question: str
    lang: str = ""
    intent: str = ""
    audience: str = ""       # lesson mode: "" (auto) | "yeshiva" | "school"
    grade_band: str = ""     # school lessons: a-c | d-f | g-i | j-l
    length: str = ""         # "" (medium) | "short" | "medium" | "long"


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    if not req.question.strip():
        raise HTTPException(status_code=422, detail="question must not be empty")
    return _run_query(req.question, req.lang, req.intent, [],
                      audience=req.audience, grade_band=req.grade_band, length=req.length)


# ── Sessions ──────────────────────────────────────────────────────────────────

class SessionOut(BaseModel):
    id: str
    first_q: str
    created_at: str
    updated_at: str | None = None


class SessionCreateOut(SessionOut):
    # The first-query result must survive serialization — a bare SessionOut
    # response_model would strip it (client then sees no `result`/`answer`).
    result: QueryResponse


@app.get("/sessions", response_model=list[SessionOut])
def list_sessions():
    return db.list_sessions()


@app.post("/sessions", response_model=SessionCreateOut, status_code=201)
def create_session(req: QueryRequest):
    """Create a new session and run the first query."""
    if not req.question.strip():
        raise HTTPException(status_code=422, detail="question must not be empty")

    sid = db.create_session(req.question.strip())
    db.save_message(sid, "user", req.question)

    result = _run_query(req.question, req.lang, req.intent, [],
                        audience=req.audience, grade_band=req.grade_band, length=req.length)

    db.save_message(
        sid,
        "assistant",
        result.answer,
        intent=result.intent,
        citations=[c.model_dump() for c in result.citations],
        caveats=result.caveats,
        grounded=result.grounded,
        files=[f.model_dump() for f in result.files],
    )

    session = db.list_sessions()
    session_row = next(s for s in session if s["id"] == sid)
    return {"id": sid, "first_q": session_row["first_q"], "created_at": session_row["created_at"],
            "result": result}


class SessionQueryResponse(QueryResponse):   # inherits lesson_plan etc.
    session_id: str


@app.post("/sessions/{session_id}/query", response_model=SessionQueryResponse)
def session_query(session_id: str, req: QueryRequest):
    """Continue an existing session."""
    if not req.question.strip():
        raise HTTPException(status_code=422, detail="question must not be empty")

    history_rows = db.get_messages(session_id)
    if not history_rows:
        raise HTTPException(status_code=404, detail="session not found")

    history = [
        Turn(role=m["role"], text=m["text"])
        for m in history_rows[-8:]
    ]

    db.save_message(session_id, "user", req.question)

    result = _run_query(req.question, req.lang, req.intent, history,
                        audience=req.audience, grade_band=req.grade_band, length=req.length)

    db.save_message(
        session_id,
        "assistant",
        result.answer,
        intent=result.intent,
        citations=[c.model_dump() for c in result.citations],
        caveats=result.caveats,
        grounded=result.grounded,
        files=[f.model_dump() for f in result.files],
    )

    return SessionQueryResponse(**result.model_dump(), session_id=session_id)


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
def get_messages(session_id: str):
    msgs = db.get_messages(session_id)
    if not msgs:
        raise HTTPException(status_code=404, detail="session not found")
    return msgs


@app.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str):
    if not db.delete_session(session_id):
        raise HTTPException(status_code=404, detail="session not found")


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
def list_lessons():
    return db.list_lessons()


@app.get("/lessons/{lesson_id}")
def get_lesson(lesson_id: str):
    lesson = db.get_lesson(lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="lesson not found")
    return lesson


@app.delete("/lessons/{lesson_id}", status_code=204)
def delete_lesson(lesson_id: str):
    if not db.delete_lesson(lesson_id):
        raise HTTPException(status_code=404, detail="lesson not found")
