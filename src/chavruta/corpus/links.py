"""Links graph + anchor chains (research D10) — task T015a.

Holds explicit cross-references (Sefaria Links) and commentary→anchor edges, and answers
"what is connected to this ref?". Powers link-based retrieval (LinkExpander) so the system
can follow the chain of transmission (pasuk → Rishonim → Acharonim → Halacha) and reach
supercommentaries — things vector similarity alone does not encode.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from chavruta.corpus.schema import Link


class LinkGraph:
    def __init__(self) -> None:
        # ref -> list[(neighbour_ref, link_type, neighbour_work_id)]
        self._adj: dict[str, list[tuple[str, str, str]]] = defaultdict(list)

    def add(self, link: Link) -> None:
        self._adj[link.from_ref].append((link.to_ref, link.link_type, link.to_work_id))
        # edges are navigable both ways for traversal
        self._adj[link.to_ref].append((link.from_ref, link.link_type, link.from_work_id))

    def add_anchor(self, commentary_ref: str, anchor_ref: str,
                   commentary_work_id: str, anchor_work_id: str) -> None:
        """Register a commentary→anchor edge (incl. supercommentary anchor chains)."""
        self.add(Link(
            from_ref=anchor_ref, to_ref=commentary_ref,
            from_work_id=anchor_work_id, to_work_id=commentary_work_id,
            link_type="commentary",
        ))

    def neighbours(self, ref: str, work_ids: list[str] | None = None) -> list[str]:
        out = []
        for neighbour_ref, _type, work_id in self._adj.get(ref, ()):
            if work_ids is None or work_id in work_ids:
                out.append(neighbour_ref)
        return out

    def expand(self, refs: list[str], depth: int = 1,
               work_ids: list[str] | None = None) -> list[str]:
        """BFS from `refs` up to `depth`, returning newly reached refs (the chain)."""
        seen = set(refs)
        frontier = list(refs)
        reached: list[str] = []
        for _ in range(max(0, depth)):
            nxt = []
            for ref in frontier:
                for neighbour in self.neighbours(ref, work_ids):
                    if neighbour not in seen:
                        seen.add(neighbour)
                        reached.append(neighbour)
                        nxt.append(neighbour)
            frontier = nxt
            if not frontier:
                break
        return reached

    # ── persistence ──
    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            for from_ref, edges in self._adj.items():
                for to_ref, link_type, work_id in edges:
                    f.write(json.dumps(
                        {"from_ref": from_ref, "to_ref": to_ref,
                         "link_type": link_type, "to_work_id": work_id},
                        ensure_ascii=False) + "\n")

    @classmethod
    def load(cls, path: str | Path) -> "LinkGraph":
        g = cls()
        p = Path(path)
        if not p.exists():
            return g
        with p.open(encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                g._adj[d["from_ref"]].append((d["to_ref"], d["link_type"], d.get("to_work_id", "")))
        return g
