"""Content denylist helpers (spec 009 R10) — defence in depth over the store-level `$not` filter.

The primary guard is the server-side `{"$not": {"work_id": [...]}}` filter that
`HybridRetriever` / `LinkExpander` add to every store call. `drop_denied` is the last line: it
removes anything whose work is denied from a list that is about to be shown, so a path that was
missed upstream still cannot leak a denied work (SC-005).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace
from functools import lru_cache
from importlib import resources

from chavruta.corpus import audience
from chavruta.corpus.audience import Denylist

NOT_KEY = "$not"


def deny_filter(deny_work_ids) -> dict:
    """The store `Filter` fragment for a denylist: {} when empty, else {"$not": {"work_id": [...]}}."""
    if not deny_work_ids:
        return {}
    return {NOT_KEY: {"work_id": sorted(deny_work_ids)}}


def with_deny(filters: dict | None, deny_work_ids) -> dict | None:
    """`filters` plus the denylist. Empty denylist returns `filters` untouched (same object)."""
    if not deny_work_ids:
        return filters
    merged = dict(filters or {})
    merged.update(deny_filter(deny_work_ids))
    return merged


def work_ids_by_ref(hits: Iterable) -> dict[str, str]:
    """{ref: work_id} from retrieved hits — the resolver for items (e.g. `Citation`) that carry a
    ref but no work_id. Pass `work_of=lambda x: mapping.get(x.ref)` to `drop_denied`."""
    out: dict[str, str] = {}
    for h in hits or ():
        ref = h.get("ref") if isinstance(h, dict) else getattr(h, "ref", "")
        wid = h.get("work_id") if isinstance(h, dict) else getattr(h, "work_id", "")
        if ref and wid:
            out[ref] = wid
    return out


def _work_id(item) -> str | None:
    if isinstance(item, dict):
        return item.get("work_id") or None
    return getattr(item, "work_id", None) or None


def drop_denied(items, deny_work_ids, *, work_of: Callable | None = None,
                keep_unknown: bool = True) -> list:
    """Items (RankedHit, Citation, dict, ...) whose work is NOT denied.

    The work is read from `work_of(item)` if given, else from the item's `work_id` (attribute or dict
    key). An item whose work cannot be determined is kept unless `keep_unknown=False` (fail closed —
    use it when every item is expected to resolve). Empty denylist returns `list(items)` unchanged.
    """
    items = list(items or [])
    if not deny_work_ids:
        return items
    deny = frozenset(deny_work_ids)
    out = []
    for it in items:
        wid = (work_of(it) if work_of is not None else None) or _work_id(it)
        if wid is None:
            if keep_unknown:
                out.append(it)
        elif wid not in deny:
            out.append(it)
    return out


# ── Entries → what to enforce, and where (spec 009 T053, R10 investigation) ────────────────────────
# `work_id` in the index is one of 15 TIER slugs, not a book. So an entry that names exactly a tier is
# cheap and exact (a Qdrant `must_not`), and an entry that names a book or a catalogue category has to
# become a set of Sefaria titles and be enforced on the way out, from the hit's ref.
_log = logging.getLogger(__name__)

TIERS = frozenset({
    "tanakh", "mishnah", "tosefta", "gemara", "yerushalmi", "midrash", "halacha", "shut", "kabbalah",
    "chasidut", "jewish_thought", "musar", "liturgy", "second_temple", "reference",
})

# Catalogue top-level categories that ARE exactly one tier (research.md R10 step 4), so they stay a
# server-side filter. `Halakhah` and `Talmud` are deliberately absent: commentary on the Talmud files
# under `gemara`/`halacha` too, so they are not exact and stay title sets.
_CATEGORY_TIER = {
    "responsa": "shut", "kabbalah": "kabbalah", "chasidut": "chasidut", "musar": "musar",
    "liturgy": "liturgy", "midrash": "midrash", "tosefta": "tosefta", "reference": "reference",
    "second temple": "second_temple", "jewish thought": "jewish_thought", "mishnah": "mishnah",
    "tanakh": "tanakh",
}

# Over-fetch factor when titles are denied: the retriever asks for this many times `top_k`, drops the
# denied titles, and keeps `top_k`. Recall under heavy denial is the cost R10 accepts for not
# backfilling a payload field.
TITLE_OVERFETCH = 3


@lru_cache(maxsize=1)
def _catalog() -> tuple[tuple[str, tuple[str, ...]], ...]:
    """[(title_en, path segments lower-cased)] for every book in corpus/data/catalog.json."""
    import json

    raw = resources.files("chavruta.corpus").joinpath("data/catalog.json").read_text(encoding="utf-8")
    return tuple((b["title_en"], _segments(b.get("path", ""))) for b in json.loads(raw).get("books", []))


def _segments(path: str) -> tuple[str, ...]:
    # Both "Chasidut/Breslov" (catalogue) and "Chasidut / Breslov" (search-index category_path).
    return tuple(p.strip().lower() for p in (path or "").split("/") if p.strip())


def resolve_denylist(entries: Iterable[tuple[str, str]]) -> Denylist:
    """`entries` are (kind, value) rows from content_denylist (`kind` is `category` or `work`).

    * a value that is a tier slug                      -> work_ids
    * a category that is exactly one tier ("Responsa")  -> work_ids
    * any other category path ("Halakhah/Mishneh Torah") -> every catalogue title at or under it
    * a book title                                      -> that title
    A value that resolves to nothing is logged and ignored (the writer of the row is meant to validate
    against the catalogue; this does not turn a typo into an outage).
    """
    work_ids: set[str] = set()
    titles: set[str] = set()
    cat = _catalog()
    for kind, value in entries:
        v = (value or "").strip()
        if not v:
            continue
        low = v.lower()
        if low in TIERS:
            work_ids.add(low)
            continue
        if kind == "work":
            hit = [t for t, _ in cat if t.lower() == low]
        else:
            seg = _segments(v)
            if len(seg) == 1 and seg[0] in _CATEGORY_TIER:
                work_ids.add(_CATEGORY_TIER[seg[0]])
                continue
            hit = [t for t, path in cat if path[:len(seg)] == seg] if seg else []
        if hit:
            titles.update(hit)
        else:
            _log.warning("content denylist entry resolves to nothing: kind=%s value=%r", kind, v[:80])
    return Denylist(work_ids=frozenset(work_ids), titles=frozenset(titles))


@lru_cache(maxsize=65536)
def _title_of(ref: str) -> str | None:
    from chavruta.corpus.refs import work_title_for_ref

    return work_title_for_ref(ref)


def _ref_of(item) -> str:
    if isinstance(item, dict):
        return item.get("ref") or (item.get("payload") or {}).get("ref") or ""
    return getattr(item, "ref", "") or (getattr(item, "payload", None) or {}).get("ref", "") or ""


def _work_id_of(item, wmap: Mapping[str, str] | None) -> str | None:
    wid = _work_id(item)
    if wid:
        return wid
    payload = item.get("payload") if isinstance(item, dict) else getattr(item, "payload", None)
    if payload and payload.get("work_id"):
        return payload["work_id"]
    return (wmap or {}).get(_ref_of(item)) or None


def drop_denied_titles(items, titles) -> list:
    """Items whose ref belongs to a denied Sefaria title. Empty set returns `items` untouched."""
    if not titles:
        return items
    return [it for it in items if _title_of(_ref_of(it)) not in titles]


def scoped_query(query):
    """`query` with the request's ambient denylist merged in. Same object when there is none, so the
    adult path is untouched. Called at the retriever's and the link expander's front doors, which is
    what makes a Query built anywhere (a fresh one in the agentic fetcher included) safe."""
    deny = audience.current().deny
    if not deny:
        return query
    wids = frozenset(query.deny_work_ids) | deny.work_ids
    tits = frozenset(query.deny_titles) | deny.titles
    if wids == query.deny_work_ids and tits == query.deny_titles:
        return query
    return replace(query, deny_work_ids=wids, deny_titles=tits)


def scoped_filters(filters: dict | None) -> dict | None:
    """`filters` plus the ambient tier denylist, for a direct `store.fetch_by_refs`. Untouched when empty."""
    return with_deny(filters, audience.current().deny.work_ids)


def drop_scoped(items, *, work_ids: Mapping[str, str] | None = None):
    """Drop whatever the ambient denylist denies: by tier (`work_id` on the item, its payload, or the
    optional {ref: work_id} map) and by title (from the ref). The last line of defence for lists about
    to be shown or cited. Returns `items` itself when nothing is denied."""
    deny = audience.current().deny
    if not deny:
        return items
    kept = drop_denied(items, deny.work_ids, work_of=lambda it: _work_id_of(it, work_ids))
    return drop_denied_titles(kept, deny.titles)
