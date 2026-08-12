"""Core data types for Chavruta.AI — the unified corpus schema (data-model.md).

One uniform `Chunk` flows through ingestion → embedding → store → retrieval → generation,
keeping the pipeline corpus-agnostic (Constitution Principle III). Both primary texts and
commentaries (including supercommentary via anchor chains) normalize into `Chunk`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


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
    # DO NOT put a licence here. Rights are per (title, language, versionTitle) on Sefaria's side and
    # do not follow work_id: Talmud Bavli's default edition is CC-BY-NC while its Aramaic base is
    # public domain, and one work can differ by language. This field once hardcoded "CC0 / Sefaria"
    # for every work, which was simply false. The real value lives per chunk (Chunk.license), read
    # from the API at fetch time; classify it with corpus/rights.py.
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
    period: str = ""                       # halachic era for primary sources without a commentator
                                           # (geonim|rishonim|acharonim|modern) — e.g. responsa
    # structural coordinates for ordering/anchoring (e.g. {"book": "Genesis", "chapter": 1, "verse": 3})
    position: dict = field(default_factory=dict)
    # commentary-only fields
    anchor_ref: str | None = None       # the ref this comments on (source OR another commentary)
    anchor_kind: AnchorKind | None = None
    commentator_id: str | None = None
    # ── Rights. Per-CHUNK, not per-work: Sefaria licenses per (title, language, versionTitle), and
    # those boundaries do not follow work_id at all. The same work can be CC-BY-NC in Hebrew and CC0
    # in English (Peninei Halakhah), and one author can span CC-BY-NC and full copyright (Steinsaltz).
    # Empty means UNKNOWN — which must be treated as "all rights reserved", never as permissive.
    license: str = ""                   # verbatim from Sefaria: "Public Domain" | "CC0" | "CC-BY" |
                                        # "CC-BY-SA" | "CC-BY-NC" | "Copyright: <holder>" | "unknown"
    version_title: str = ""             # the exact edition the text came from — the audit trail

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
            "period": self.period,
            "position": self.position,
            "anchor_ref": self.anchor_ref,
            "anchor_kind": self.anchor_kind.value if self.anchor_kind else None,
            "commentator_id": self.commentator_id,
            # Indexed so retrieval can filter by rights (e.g. exclude NonCommercial for paid users)
            # and so the source sheet can attribute the actual edition, not a generic "Sefaria".
            "license": self.license,
            "version_title": self.version_title,
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
    commentator_id: str | None = None


@dataclass
class Turn:
    role: str   # "user" | "assistant"
    text: str
    # Refs this turn CITED (assistant turns only). A study conversation converges on a sugya over
    # several turns, and the surest record of which sugya is what the earlier answers already
    # grounded themselves in — far more reliable than re-deriving it from the wording of a
    # follow-up like "האם הם חולקים?". Optional and empty by default: a caller that does not
    # track citations keeps the old two-field behaviour.
    refs: list[str] = field(default_factory=list)


@dataclass
class Query:
    text: str
    lang: str = "he"
    intent: Intent = Intent.QA
    work_ids: list[str] | None = None         # corpus scoping; None = all loaded
    commentator_ids: list[str] | None = None  # named-commentator bias/filter
    named_refs: list[str] | None = None       # explicit verse refs detected in the question
    requested_works: list[str] | None = None  # works the question explicitly asks about
    expand_links: bool = False                   # follow Link edges + anchor chains
    expand_depth: int = 1
    search_text: str = ""                        # text used for retrieval (trigger phrases like
                                                 # "prepare a lesson on" stripped); falls back to `text`
    # Tractates the question NAMES explicitly ("במסכת סוכה", "סוכה מא") but without enough detail to
    # resolve a ref. Weaker than named_refs and used differently: it scopes a sub-search to that
    # tractate rather than anchoring, so "what does Rashi say in Sukkah" can reach Rashi on Sukkah
    # even when the daf is never given.
    tractates: list[str] | None = None


@dataclass
class LessonSection:
    heading: str
    role: str = "branch"                    # "opening" | "branch" | "convergence" (spec 003)
    source_refs: list[str] = field(default_factory=list)
    explanation: str = ""
    discussion_points: list[str] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)


@dataclass
class LessonPlan:
    topic: str
    sections: list[LessonSection] = field(default_factory=list)
    template_id: str = ""                   # which template shaped the arc (spec 003)
    is_open: bool = False                   # True → the sugya does not converge to a conclusion


@dataclass
class Answer:
    text: str
    citations: list[Citation] = field(default_factory=list)
    grounded: bool = False
    no_source: bool = False
    caveats: list[str] = field(default_factory=list)
    intent: Intent = Intent.QA
    lesson_plan: LessonPlan | None = None
