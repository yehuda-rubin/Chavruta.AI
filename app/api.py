# -*- coding: utf-8 -*-
"""Chavruta.AI — Nebius Serverless Endpoint (FastAPI).

REST wrapper over ChavrutaPipeline for deployment as a Nebius Serverless Endpoint.
The pipeline is loaded once at startup and shared across requests.

    uvicorn app.api:app --host 0.0.0.0 --port 8080
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

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
    _get_pipeline()        # warm up bge-m3 + Qdrant connection at startup
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


class QueryResponse(BaseModel):
    answer: str
    citations: list[CitationOut]
    grounded: bool
    intent: str
    caveats: list[str] = []
    lesson_plan: LessonPlanOut | None = None   # the lesson arc (spec 003), present for LESSON


def _run_query(question: str, lang: str, intent_str: str, history: list[Turn]) -> QueryResponse:
    intent = None
    if intent_str:
        try:
            intent = Intent(intent_str)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"unknown intent: {intent_str!r}")

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

    return QueryResponse(
        answer=answer.text,
        citations=[_cite(c) for c in answer.citations],
        grounded=answer.grounded,
        intent=answer.intent.value if answer.intent else "qa",
        caveats=list(answer.caveats),
        lesson_plan=lesson_plan,
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
