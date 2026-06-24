"""Arc-structured lesson builder (spec 003, Phase 2).

Maps retrieved hits onto a template's stages (opening → branches → convergence) by source
kind, producing a `LessonPlan` whose sections follow the narrative arc — every section
grounded in real citations, empty stages omitted (no invented sections, Principle I).
"""

from __future__ import annotations

from chavruta.corpus.schema import Citation, LessonPlan, LessonSection
from chavruta.lessons.templates import Stage, Template
from chavruta.retrieval.base import RankedHit

# Commentator tiers — used to classify a commentary hit as Rishonim vs Acharonim.
_ACHARONIM = {
    "malbim", "or_hachaim", "metzudat_david", "metzudat_zion", "sforno",
    "kli_yakar", "shach", "taz", "mishnah_berurah",
}

# Halachic era → source kind, for primary sources that carry a `period` instead of a
# commentator (responsa). Geonim are folded into rishonim, modern poskim into acharonim,
# so a teshuva slots into the rishonim/acharonim stages of ANY template (lessons, not just
# the שו"ת set) — responsa are cited everywhere, the same way they are in real shiurim.
_PERIOD_KIND = {
    "geonim": "rishonim", "rishonim": "rishonim",
    "acharonim": "acharonim", "modern": "acharonim",
}


def hit_kind(h: RankedHit) -> str:
    """Classify a hit into a source kind matching the templates' `source_kinds` vocabulary."""
    if h.commentator_id:
        cid = h.commentator_id.lower()
        return "acharonim" if cid in _ACHARONIM else "rishonim"
    if getattr(h, "period", None):
        return _PERIOD_KIND.get(h.period.lower(), "acharonim")
    work = (h.work_id or "").lower()
    if "mishnah" in work:
        return "mishnah"
    if "talmud" in work or "bavli" in work or "gemara" in work:
        return "gemara"
    if "midrash" in work:
        return "midrash"
    return "pasuk"


def _section(stage: Stage, hits: list[RankedHit]) -> LessonSection:
    from chavruta.generation.grounded import source_body

    return LessonSection(
        heading=stage.title_he,
        role=stage.key,
        source_refs=[h.ref for h in hits],
        citations=[
            Citation(chunk_id=h.chunk_id, ref=h.ref, deep_link=h.deep_link,
                     quote=source_body(h.text)[:280], commentator_id=h.commentator_id)
            for h in hits
        ],
    )


# A generous per-stage cap on candidate sources fed to the walkthrough — bounds the prompt
# without starving it (a big sugya legitimately needs many sources, and a long generation is
# fine). The output keeps ONLY what the walkthrough actually cites (prune_lesson_to_cited),
# so relevance is enforced after generation, not by a tight pre-cap.
_BRANCH_CAP = 12
_CONVERGENCE_CAP = 6


def build_lesson_from_template(topic: str, template: Template, hits: list[RankedHit],
                               anchor_refs: list[str] | None = None) -> LessonPlan:
    """Lay the (score-ordered) hits onto the template's arc.

    opening → the source at the START of the sugya (Phase 4: prefer a hit on `anchor_refs`,
    the anchor pesukim the retrieval hung on, so the lesson opens where the sugya actually
    begins — not merely the highest-scored source); branches → remaining sources distributed
    round-robin across the branch stages that want their kind (keeps the "multiple
    directions" shape even when two branches share a kind); convergence → conclusion sources.
    Empty stages are dropped; `is_open` is set when no convergence section materialises.
    """
    kinds = [(h, hit_kind(h)) for h in hits]
    anchors = set(anchor_refs or [])
    used: set[int] = set()
    sections: list[LessonSection] = []

    # opening — the start of the sugya: prefer an anchor source, else the top matching hit
    opening = template.opening
    if opening:
        chosen = None
        if anchors:
            chosen = next(
                (i for i, (h, k) in enumerate(kinds)
                 if k in opening.source_kinds and (h.ref in anchors or (h.anchor_ref or "") in anchors)),
                None,
            )
        if chosen is None:
            chosen = next(
                (i for i, (h, k) in enumerate(kinds) if k in opening.source_kinds), None
            )
        if chosen is not None:
            sections.append(_section(opening, [kinds[chosen][0]]))
            used.add(chosen)

    # convergence reservation — set aside ONE matching source for the conclusion BEFORE the
    # branches run, so a teshuva (or shiur) actually reaches its pesak even when a branch
    # shares the convergence kind (e.g. poskim appear both in the discussion and the ruling).
    # The LAST eligible hit is reserved (lowest-scored), leaving the stronger ones for branches.
    convergence = template.convergence
    reserved_conv = None
    if convergence:
        reserved_conv = next(
            (i for i in reversed(range(len(kinds)))
             if i not in used and kinds[i][1] in convergence.source_kinds),
            None,
        )
        if reserved_conv is not None:
            used.add(reserved_conv)

    # branches — round-robin remaining hits across the branch stages that want their kind
    branches = template.branches
    if branches:
        buckets: dict[int, list[RankedHit]] = {idx: [] for idx in range(len(branches))}
        rr = 0
        for i, (h, k) in enumerate(kinds):
            if i in used:
                continue
            eligible = [bi for bi, s in enumerate(branches) if k in s.source_kinds]
            if not eligible:
                continue
            chosen = eligible[rr % len(eligible)]
            buckets[chosen].append(h)
            used.add(i)
            rr += 1
        for bi, stage in enumerate(branches):
            if buckets[bi]:
                sections.append(_section(stage, buckets[bi][:_BRANCH_CAP]))

    # convergence — the reserved hit plus any other still-unused matching sources
    if convergence:
        conv_hits = ([kinds[reserved_conv][0]] if reserved_conv is not None else []) + [
            h for i, (h, k) in enumerate(kinds)
            if i not in used and i != reserved_conv and k in convergence.source_kinds
        ]
        if conv_hits:
            sections.append(_section(convergence, conv_hits[:_CONVERGENCE_CAP]))

    is_open = not any(s.role == "convergence" for s in sections)
    return LessonPlan(topic=topic, sections=sections,
                      template_id=template.template_id, is_open=is_open)
