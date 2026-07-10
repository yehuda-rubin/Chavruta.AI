# -*- coding: utf-8 -*-
"""check_templates.py — validate EVERY lesson/shut template end to end (NO LLM API).

For each template folder under lessons/templates/:
  1. manifest.yaml parses and has the required fields;
  2. every file it declares actually exists and is non-trivial;
  3. it is present in the template RAG and its OWN example queries route back to it
     (under the correct audience / grade-band filter — the same filter the live app uses).

    docker compose up -d qdrant
    .venv/Scripts/python.exe scripts/check_templates.py
"""
from __future__ import annotations

import torch  # noqa: F401 — first (native DLL order)
import os
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
TDIR = REPO / "lessons" / "templates"
os.environ.setdefault("CHAVRUTA_QDRANT_URL", "http://localhost:6333")
QURL = os.environ["CHAVRUTA_QDRANT_URL"]
COLL = os.environ.get("CHAVRUTA_TEMPLATES_COLLECTION", "chavruta_templates")

REQUIRED = ["id", "title", "audience", "mode", "when_to_use", "keywords", "files"]


def main() -> None:
    folders = sorted(p for p in TDIR.iterdir() if (p / "manifest.yaml").exists())
    print(f"Found {len(folders)} template folders under {TDIR.relative_to(REPO)}\n")

    file_errors, manifests = [], {}
    for d in folders:
        m = yaml.safe_load((d / "manifest.yaml").read_text(encoding="utf-8"))
        tid = m.get("id") or d.name
        manifests[tid] = (d, m)
        missing = [k for k in REQUIRED if not m.get(k)]
        if missing:
            file_errors.append(f"  ✗ {d.name}: manifest missing {missing}")
        for role, fname in (m.get("files") or {}).items():
            fp = d / fname
            if not fp.exists():
                file_errors.append(f"  ✗ {d.name}: declared file '{fname}' ({role}) not found")
            elif len(fp.read_text(encoding='utf-8').strip()) < 120:
                file_errors.append(f"  ✗ {d.name}: file '{fname}' looks empty/too short")

    print("── 1) FILE + MANIFEST COMPLETENESS ──")
    print("  ✓ all folders have valid manifests + files" if not file_errors else "\n".join(file_errors))

    # ── RAG self-routing ──
    from chavruta.embedding.bge_m3 import BgeM3Embedding
    emb = BgeM3Embedding(use_sparse=False); emb.embed_query("warmup")
    from qdrant_client import QdrantClient, models
    client = QdrantClient(url=QURL, timeout=120)
    n_indexed = client.count(COLL, exact=True).count
    print(f"\n── 2) RAG SELF-ROUTING (collection '{COLL}', {n_indexed} points) ──")

    def route(query, audience, band):
        must = []
        if audience:
            must.append(models.FieldCondition(key="audience", match=models.MatchValue(value=audience)))
        if band:
            must.append(models.FieldCondition(key="grade_band", match=models.MatchValue(value=band)))
        qf = models.Filter(must=must) if must else None
        r = client.query_points(COLL, query=emb.embed_query(query).dense, limit=1,
                                query_filter=qf, with_payload=True)
        return (r.points[0].payload.get("id"), round(r.points[0].score, 3)) if r.points else (None, 0)

    total_q = hit_q = 0
    per_tpl = []
    for tid, (d, m) in manifests.items():
        aud = m.get("audience")
        band = m.get("grade_band") if aud == "school" else None
        queries = list(m.get("example_queries", [])) + list(m.get("example_topics", []))
        if not queries:
            per_tpl.append((tid, aud, band, 0, 0, [])); continue
        ok, miss = 0, []
        for q in queries:
            top, sc = route(q, aud, band)
            total_q += 1
            if top == tid:
                ok += 1; hit_q += 1
            else:
                miss.append(f"{q!r}→{top}")
        per_tpl.append((tid, aud, band, ok, len(queries), miss))

    for tid, aud, band, ok, n, miss in per_tpl:
        mark = "✓" if ok == n else ("~" if ok else "✗")
        tag = f"{aud}/{band}" if band else aud
        line = f"  {mark} {tid:26s} [{tag:16s}] self-route {ok}/{n}"
        if miss:
            line += "   misses: " + "; ".join(miss[:3]) + ("…" if len(miss) > 3 else "")
        print(line)

    print(f"\nSUMMARY: {len(folders)} templates · file/manifest errors: {len(file_errors)} · "
          f"self-route {hit_q}/{total_q} example queries ({round(100*hit_q/max(total_q,1))}%)")


if __name__ == "__main__":
    main()
