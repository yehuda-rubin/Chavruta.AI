"""Lesson templates (spec 003, Phase 1) — the "second RAG".

A small, hand-authored corpus of structural skeletons (opening → branches → convergence)
is retrieved by topic and later filled with grounded sources from the MAIN corpus. The
templates encode *structure only* (no copyrighted shiur text), so adding/curating them is
a pure data/config operation (Principle III).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "lesson_templates.yaml"


@dataclass
class Stage:
    key: str                      # "opening" | "branch" | "convergence"
    title_he: str
    source_kinds: list[str] = field(default_factory=list)


@dataclass
class Template:
    template_id: str
    name_he: str
    when_to_use: str              # natural-language trigger — embedded for retrieval
    stages: list[Stage] = field(default_factory=list)

    @property
    def opening(self) -> Stage | None:
        return next((s for s in self.stages if s.key == "opening"), None)

    @property
    def branches(self) -> list[Stage]:
        return [s for s in self.stages if s.key == "branch"]

    @property
    def convergence(self) -> Stage | None:
        return next((s for s in self.stages if s.key == "convergence"), None)


def load_templates(path: str | Path | None = None) -> list[Template]:
    p = Path(path) if path else DEFAULT_PATH
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or []
    out: list[Template] = []
    for t in raw:
        stages = [
            Stage(key=s["key"], title_he=s["title_he"], source_kinds=list(s.get("source_kinds", [])))
            for s in t.get("stages", [])
        ]
        out.append(Template(
            template_id=t["template_id"], name_he=t["name_he"],
            when_to_use=t["when_to_use"], stages=stages,
        ))
    return out


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


def select_template(topic: str, embedding, templates: list[Template]) -> Template | None:
    """Pick the template whose `when_to_use` is closest to the topic (cosine over `embedding`)."""
    if not templates:
        return None
    qv = embedding.embed_query(topic).dense
    return max(templates, key=lambda t: _cosine(qv, embedding.embed_query(t.when_to_use).dense))


class TemplateIndex:
    """Caches the templates' embeddings so selection is one query-embed per call."""

    def __init__(self, templates: list[Template], embedding):
        self.templates = templates
        self.embedding = embedding
        self._vecs = [embedding.embed_query(t.when_to_use).dense for t in templates]

    def select(self, topic: str) -> Template | None:
        if not self.templates:
            return None
        qv = self.embedding.embed_query(topic).dense
        scored = zip(self.templates, self._vecs)
        return max(scored, key=lambda tv: _cosine(qv, tv[1]))[0]
