# -*- coding: utf-8 -*-
"""Backfill a nikud/ktiv-normalised `search_he` payload field + full-text index.

No re-embedding: we only add a searchable text field (corpus.normalize.normalize_he
of text_he/text) and a Qdrant full-text index on it, so plain plene queries match the
vocalised corpus on the lexical channel.

    python scripts/backfill_search_he.py            # full corpus (~449k points)
    SMOKE=mishnah python scripts/backfill_search_he.py   # only work_id=mishnah (fast test)

Idempotent and resumable: re-running overwrites search_he with the same value.
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chavruta.corpus.normalize import normalize_he
from chavruta.store.qdrant_store import QdrantStore

URL = os.environ.get("CHAVRUTA_QDRANT_URL", "http://localhost:6333")
COLLECTION = os.environ.get("CHAVRUTA_COLLECTION", "chavruta")
SMOKE = os.environ.get("SMOKE", "").strip()          # e.g. "mishnah" → only that work
PAGE = int(os.environ.get("PAGE", "2000"))
FLUSH = int(os.environ.get("FLUSH", "4000"))

store = QdrantStore(mode="server", url=URL)
client = store._client_()
from qdrant_client import models

store.ensure_text_index(COLLECTION, "search_he")
print(f"[index] full-text index ensured on search_he ({COLLECTION})")

# Select only points still MISSING search_he, so re-runs resume cheaply (idempotent).
must = [models.IsEmptyCondition(is_empty=models.PayloadField(key="search_he"))]
if SMOKE:
    must.append(models.FieldCondition(key="work_id", match=models.MatchValue(value=SMOKE)))
    print(f"[smoke] limiting to work_id={SMOKE!r}")
scroll_filter = models.Filter(must=must)

total = client.count(COLLECTION, count_filter=scroll_filter, exact=True).count
print(f"[scan] {total} points to backfill")

ops: list = []
done = skipped = 0
offset = None
t0 = time.time()


def flush():
    global ops
    if ops:
        client.batch_update_points(collection_name=COLLECTION, update_operations=ops, wait=True)
        ops = []


while True:
    points, offset = client.scroll(
        collection_name=COLLECTION, scroll_filter=scroll_filter, limit=PAGE,
        offset=offset, with_payload=["text_he", "text"], with_vectors=False,
    )
    if not points:
        break
    for p in points:
        pl = p.payload or {}
        norm = normalize_he(pl.get("text_he") or pl.get("text") or "")
        if not norm:
            skipped += 1
            continue
        ops.append(models.SetPayloadOperation(
            set_payload=models.SetPayload(payload={"search_he": norm}, points=[p.id])))
        done += 1
        if len(ops) >= FLUSH:
            flush()
    rate = done / max(time.time() - t0, 1e-9)
    print(f"  {done}/{total} updated ({skipped} empty)  {rate:.0f}/s", flush=True)
    if offset is None:
        break

flush()
print(f"[done] {done} updated, {skipped} empty, {time.time()-t0:.0f}s")
