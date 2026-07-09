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

# Source markers ([S1], [S1, S5], …) are the grounding mechanism — the pipeline maps them to
# citations, then we strip them from the DISPLAYED text so the answer reads cleanly.
_MARKER_RE = re.compile(r"\s*\[\s*S\d+(?:\s*,\s*S\d+)*\s*\]")


def _strip_markers(text: str) -> str:
    return re.sub(r"[ \t]{2,}", " ", _MARKER_RE.sub("", text or "")).strip()

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


_LESSON_SPLIT_RE = re.compile(r"^===(SOURCE_SHEET|LESSON_FLOW|FULL_LESSON|ORDER)===\s*$", re.M)


def _lesson_job_md(question: str, hits, lang: str) -> str:
    """The bridge job that asks Claude to WRITE all three lesson files (deep iyun)."""
    lines = [f"lang: {lang}", "", "## TOPIC", question.strip(), "", "## SOURCES"]
    for i, h in enumerate(hits, 1):
        who = f" ({h.commentator_id})" if getattr(h, "commentator_id", None) else ""
        lines += [f"### [S{i}] {h.ref}{who}", (getattr(h, "text", "") or "").strip(), ""]
    lines += [
        "## INSTRUCTIONS FOR CLAUDE — write a FULL IYUN lesson (four parts)",
        "Write ONE answer with these parts, separated by these EXACT delimiter lines:",
        "===SOURCE_SHEET===", "===LESSON_FLOW===", "===FULL_LESSON===", "===ORDER===", "",
        "SOURCE_SHEET — the sources ARRANGED IN THE ORDER THEY ARE DISCUSSED in the lesson "
        "(1 = the first source taught, then 2, …). For each: a number, its reference, and its full text.",
        "LESSON_FLOW — a clear, detailed outline following the classic yeshiva (Har Etzion / Brisk) "
        "iyun arc: (0) הצגת הסוגיה, (1) העמדת החקירה, (2) שיטות הראשונים, (3) האחרונים, (4) נפקא מינה, "
        "(5) סיכום. For each stage: the guiding question, which source is brought, and what is asked/answered.",
        "FULL_LESSON — a full beit-midrash IYUN shiur in the classic yeshiva style (Har Etzion / Brisk), "
        "written out in depth and at length: "
        "(a) **הצגת הסוגיה** — open straight from the source and frame the sugya; "
        "(b) **העמדת החקירה** — sharpen a central lamdanic חקירה with TWO clearly-named sides "
        "('צד א׳... לעומת צד ב׳...'); "
        "(c) **שיטות הראשונים** — bring each rishon, explain it, and show to which side of the חקירה it falls; "
        "(d) **העמקה עם האחרונים** — the conceptual formulation that sharpens the two sides; "
        "(e) **נפקא מינה** — concrete ramifications that distinguish the sides; "
        "(f) **סיכום** — the yesod to take away. "
        "Throughout: present each שיטה, raise קושיות and answer them where possible, and progress step "
        "by step. A real, long shiur — not a summary.",
        "ORDER — a single line listing the source markers in the exact order they are discussed, "
        "e.g. 'S3, S1, S5'. The backend orders the sources panel by this list.",
        "",
        "Rules: ground everything ONLY in the SOURCES; cite by [S#] (the markers build the sources "
        "panel and are stripped from the shown text); write in the question's language; **bold** key terms.",
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


def _run_lesson(question: str, lang: str) -> QueryResponse:
    """Dedicated LESSON path: real RAG retrieval → Claude writes all 3 files (deep iyun) via the
    bridge → 3 Word files + only-cited sources (in discussion order). No chat text."""
    pipeline = _get_pipeline()
    q = Query(text=question, lang=lang or None, intent=Intent.LESSON)
    rq = pipeline._resolve_query(q)
    lang = rq.lang or lang or "he"
    result = pipeline.retriever.retrieve(rq, top_k=16)
    hits = list(result.hits)
    if not hits:
        msg = "לא נמצאו מקורות לנושא זה." if lang != "en" else "No sources found for this topic."
        return QueryResponse(answer=msg, citations=[], grounded=False, intent="lesson", files=[])

    raw = pipeline.llm.request(_lesson_job_md(question, hits, lang)) if hasattr(pipeline.llm, "request") else ""
    ss, lf, fl, order = _split_lesson(raw)
    if not (ss or lf or fl):
        fl = raw

    # sources panel order = the model's explicit ORDER list; else the order first cited in the text.
    nums = [int(n) for n in re.findall(r"S(\d+)", order)] or \
           [int(n) for n in re.findall(r"\[\s*S(\d+)\s*\]", raw)]
    used, seen = [], set()
    for i in nums:
        if 1 <= i <= len(hits) and i not in seen:
            seen.add(i)
            h = hits[i - 1]
            used.append(CitationOut(ref=h.ref, text_he=(getattr(h, "text", "") or ""), text_en="",
                                    commentator=(getattr(h, "commentator_id", "") or ""),
                                    deep_link=(getattr(h, "deep_link", "") or "")))
    ss, lf, fl = _strip_markers(ss), _strip_markers(lf), _strip_markers(fl)

    he = lang != "en"
    names = (["דף_מקורות.doc", "מהלך_השיעור.doc", "השיעור_המלא.doc"] if he
             else ["source_sheet.doc", "lesson_flow.doc", "full_lesson.doc"])
    titles = ([f"דף מקורות — {question}", f"מהלך השיעור — {question}", f"שיעור מלא — {question}"] if he
              else [f"Source Sheet — {question}", f"Lesson Flow — {question}", f"Full Lesson — {question}"])
    files = [FileOut(name=names[i], title=titles[i], content=[ss, lf, fl][i]) for i in range(3)]
    return QueryResponse(answer="", citations=used, grounded=bool(used), intent="lesson", files=files)


def _run_query(question: str, lang: str, intent_str: str, history: list[Turn]) -> QueryResponse:
    if intent_str == "shut":          # UI's responsa mode → HALACHA intent
        intent_str = "halacha"
    intent = None
    if intent_str:
        try:
            intent = Intent(intent_str)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"unknown intent: {intent_str!r}")

    if intent == Intent.LESSON:            # lesson mode → Claude writes the 3 files (deep iyun)
        return _run_lesson(question, lang)

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


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    if not req.question.strip():
        raise HTTPException(status_code=422, detail="question must not be empty")
    return _run_query(req.question, req.lang, req.intent, [])


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

    result = _run_query(req.question, req.lang, req.intent, [])

    db.save_message(
        sid,
        "assistant",
        result.answer,
        intent=result.intent,
        citations=[c.model_dump() for c in result.citations],
        caveats=result.caveats,
        grounded=result.grounded,
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

    result = _run_query(req.question, req.lang, req.intent, history)

    db.save_message(
        session_id,
        "assistant",
        result.answer,
        intent=result.intent,
        citations=[c.model_dump() for c in result.citations],
        caveats=result.caveats,
        grounded=result.grounded,
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
