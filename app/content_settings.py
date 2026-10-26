"""Which books and categories are switched off for a minor (spec 009 US4, FR-020..FR-023a).

Two writers, one table (`content_denylist`): a school's admin (scope_kind='org', scope_id=org_id) and a
linked parent (scope_kind='parent', scope_id=the child's owner id). Each side replaces only its OWN
scope's set, and the effective denylist for a minor is the union (`minors.effective_denylist_rows`), so
neither side can lift the other's restriction.

What an entry may name is fixed by the catalogue (`chavruta/corpus/data/catalog.json`) plus the 15
retrieval tier slugs. Anything else is refused up front rather than stored and silently ignored later:
a typo in a safeguarding control must be visible to the person who typed it.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

import app.db as db
import app.orgs as orgs
from chavruta.retrieval.denylist import TIERS

KINDS = ("category", "work")
MAX_ENTRIES = 2000


class InvalidEntries(ValueError):
    """`bad` lists the entries that name nothing in the catalogue."""

    def __init__(self, bad: list[dict[str, Any]]):
        super().__init__(f"{len(bad)} unknown entries")
        self.bad = bad


@lru_cache(maxsize=1)
def _catalog() -> dict[str, Any]:
    raw = resources.files("chavruta.corpus").joinpath("data/catalog.json").read_text(encoding="utf-8")
    return json.loads(raw)


@lru_cache(maxsize=1)
def _valid() -> tuple[frozenset[str], frozenset[str]]:
    cat = _catalog()
    return frozenset(cat.get("categories", {})), frozenset(b["title_en"] for b in cat.get("books", []))


def validate(entries: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Normalise `[{kind, value}]` to unique (kind, value) pairs, or raise InvalidEntries."""
    cats, works = _valid()
    out: dict[tuple[str, str], None] = {}
    bad: list[dict[str, Any]] = []
    for e in entries:
        kind, value = str(e.get("kind", "")), str(e.get("value", "")).strip()
        known = (kind == "category" and value in cats) or (kind == "work" and value in works) \
            or (kind in KINDS and value in TIERS)
        if known:
            out[(kind, value)] = None
        else:
            bad.append({"kind": kind, "value": value[:80]})
    if bad:
        raise InvalidEntries(bad)
    return list(out)


def get_disabled(scope_kind: str, scope_id: str) -> list[tuple[str, str]]:
    with db._LOCK:
        rows = db.get_conn().execute(
            "SELECT kind, value FROM content_denylist WHERE scope_kind=? AND scope_id=? "
            "ORDER BY kind, value", (scope_kind, scope_id)).fetchall()
    return [(r["kind"], r["value"]) for r in rows]


def set_disabled(scope_kind: str, scope_id: str, entries: list[tuple[str, str]], set_by: str) -> None:
    """Replace this scope's set. All-or-nothing: one transaction."""
    now = db._now()
    with db._tx(db.get_conn()) as conn:
        conn.execute("DELETE FROM content_denylist WHERE scope_kind=? AND scope_id=?",
                     (scope_kind, scope_id))
        conn.executemany(
            "INSERT INTO content_denylist (scope_kind, scope_id, kind, value, set_by, set_at) "
            "VALUES (?,?,?,?,?,?)", [(scope_kind, scope_id, k, v, set_by, now) for k, v in entries])


def log_change(scope_kind: str, scope_id: str, actor: str, count: int) -> None:
    """Every change is logged (FR-021, FR-023a): org changes to `org_access_log` under the org; a
    parent's under the shared 'parent' bucket with the child as target (so account deletion anonymises
    both ids and no child id lives in the org column)."""
    action = f"content:set:{count}"
    if scope_kind == "org":
        orgs.log_access(scope_id, actor, action)
    else:
        orgs.log_access("parent", actor, action, scope_id)


def tree(disabled: list[tuple[str, str]]) -> list[dict[str, Any]]:
    """Category tree with books, each node `{id, kind, label_he, label_en, enabled, ...}`.

    `enabled` is false when the node itself is switched off OR any ancestor category is. A tier slug
    entry is not a node of this tree (it is a coarser switch the API accepts but the UI does not draw)."""
    cat = _catalog()
    off_cat = {v for k, v in disabled if k == "category"}
    off_work = {v for k, v in disabled if k == "work"}
    nodes: dict[str, dict[str, Any]] = {}
    for path in sorted(cat.get("categories", {})):
        lab = cat["categories"][path]
        nodes[path] = {"id": path, "kind": "category", "label_he": lab.get("he", ""),
                       "label_en": lab.get("en", ""), "enabled": True, "children": [], "books": []}
    roots: list[dict[str, Any]] = []

    def parent_of(path: str) -> dict[str, Any] | None:
        while "/" in path:
            path = path.rsplit("/", 1)[0]
            if path in nodes:
                return nodes[path]
        return None

    for path, node in nodes.items():
        par = parent_of(path)
        (par["children"] if par else roots).append(node)

    def blocked(path: str) -> bool:
        parts = path.split("/")
        return any("/".join(parts[:i]) in off_cat for i in range(1, len(parts) + 1))

    for path, node in nodes.items():
        node["enabled"] = not blocked(path)
    for b in cat.get("books", []):
        owner = nodes.get(b.get("path", "")) or parent_of(b.get("path", "") + "/x")
        entry = {"id": b["title_en"], "kind": "work", "label_he": b.get("title_he", ""),
                 "label_en": b["title_en"],
                 "enabled": b["title_en"] not in off_work and not blocked(b.get("path", ""))}
        if owner is not None:
            owner["books"].append(entry)
        else:
            roots.append(entry)
    return roots


def as_json(disabled: list[tuple[str, str]]) -> list[dict[str, str]]:
    return [{"kind": k, "value": v} for k, v in disabled]
