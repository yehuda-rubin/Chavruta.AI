"""Core data types for Chavruta.AI — the unified corpus schema (data-model.md).

One uniform `Chunk` flows through ingestion → embedding → store → retrieval → generation,
keeping the pipeline corpus-agnostic (Constitution Principle III). Both primary texts and
commentaries (including supercommentary via anchor chains) normalize into `Chunk`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class UnitType(str, Enum):
    SOURCE = "source"
    COMMENTARY = "commentary"


class AnchorKind(str, Enum):
    SOURCE = "source"          # commentary on a primary text
    COMMENTARY = "commentary"  # supercommentary: commentary on another commentary


class Intent(str, Enum):
    QA = "qa"
    EXPLAIN = "explain"
    COMPARE = "compare"
    LESSON = "lesson"
    HALACHA = "halacha"        # reserved / deferred until a halachic corpus is loaded


@dataclass(frozen=True)
class Work:
    """A body of texts added as a unit (Tanakh today; Gemara/Halacha/Emunah later)."""

    work_id: str
    title_he: str
    title_en: str = ""
    kind: str = "scripture"            # scripture | commentary_collection | talmud | halacha | emunah
    languages: tuple[str, ...] = ("he", "en")
    reference_scheme: str = "book/chapter/verse"
    source_adapter: str = "sefaria"
    license: str = ""
    attribution: str = ""
    version: str = ""
    fetched_at: str = ""


@dataclass(frozen=True)
class Commentator:
    commentator_id: str
    name_he: str
    name_en: str = ""
    aliases: tuple[str, ...] = ()


@dataclass
class Chunk:
    """The indexed unit. Source texts and commentaries both normalize into this."""

    chunk_id: str
    work_id: str
    unit_type: UnitType
    ref: str
    lang: str                              # "he" | "en" — one chunk per language
    text: str                              # the chunk text in `lang`
    text_he: str = ""                      # always present (Hebrew is first-class — Principle IV)
    text_en: str = ""
    deep_link: str = ""
    # structural coordinates for ordering/anchoring (e.g. {"book": "Genesis", "chapter": 1, "verse": 3})
    position: dict = field(default_factory=dict)
    # commentary-only fields
    anchor_ref: Optional[str] = None       # the ref this comments on (source OR another commentary)
    anchor_kind: Optional[AnchorKind] = None
    commentator_id: Optional[str] = None

    def to_payload(self) -> dict:
        """Metadata stored alongside the vector (and returned on search hits)."""
        return {
            "chunk_id": self.chunk_id,
            "work_id": self.work_id,
            "unit_type": self.unit_type.value,
            "ref": self.ref,
            "lang": self.lang,
            "text": self.text,
            "text_he": self.text_he,
            "text_en": self.text_en,
            "deep_link": self.deep_link,
            "position": self.position,
            "anchor_ref": self.anchor_ref,
            "anchor_kind": self.anchor_kind.value if self.anchor_kind else None,
            "commentator_id": self.commentator_id,
        }

    def validate(self) -> None:
        """Schema invariants (data-model.md rules)."""
        if not self.text or not self.text.strip():
            raise ValueError(f"chunk {self.chunk_id}: empty text is not indexable")
        if self.unit_type is UnitType.COMMENTARY:
            if not self.commentator_id:
                raise ValueError(f"chunk {self.chunk_id}: commentary requires commentator_id")
            if not self.anchor_ref:
                raise ValueError(f"chunk {self.chunk_id}: commentary requires anchor_ref")


@dataclass(frozen=True)
class Link:
    """An explicit cross-reference edge (Sefaria Links graph). Powers link-based retrieval."""

    from_ref: str
    to_ref: str
    from_work_id: str
    to_work_id: str
    link_type: str = "commentary"          # commentary | quotation | reference | halacha


@dataclass(frozen=True)
class Citation:
    """The link between a claim in an answer and the chunk it is grounded in (Principle I)."""

    chunk_id: str
    ref: str
    deep_link: str
    quote: str = ""
    commentator_id: Optional[str] = None


@dataclass
class Turn:
    role: str   # "user" | "assistant"
    text: str


@dataclass
class Query:
    text: str
    lang: str = "he"
    intent: Intent = Intent.QA
    work_ids: Optional[list[str]] = None         # corpus scoping; None = all loaded
    commentator_ids: Optional[list[str]] = None  # named-commentator bias/filter
    named_refs: Optional[list[str]] = None       # explicit verse refs detected in the question
    requested_works: Optional[list[str]] = None  # works the question explicitly asks about
    expand_links: bool = False                   # follow Link edges + anchor chains
    expand_depth: int = 1


@dataclass
class LessonSection:
    heading: str
    source_refs: list[str] = field(default_factory=list)
    explanation: str = ""
    discussion_points: list[str] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)


@dataclass
class LessonPlan:
    topic: str
    sections: list[LessonSection] = field(default_factory=list)


@dataclass
class Answer:
    text: str
    citations: list[Citation] = field(default_factory=list)
    grounded: bool = False
    no_source: bool = False
    caveats: list[str] = field(default_factory=list)
    intent: Intent = Intent.QA
    lesson_plan: Optional[LessonPlan] = None
