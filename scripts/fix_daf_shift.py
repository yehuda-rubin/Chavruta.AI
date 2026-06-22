# -*- coding: utf-8 -*-
"""fix_daf_shift.py — correct the corpus-wide off-by-one Talmud daf labelling.

Every Talmud ref is +1 daf: corpus `Bava Metzia.3a.1` holds real `Bava Metzia.2a.1`
("שניים אוחזין"). Content + vectors are correct; only the daf NUMBER in refs is wrong.
This shifts daf N → N−1 everywhere, WITHOUT re-embedding:

    python scripts/fix_daf_shift.py qdrant                       # live local Qdrant payloads
    python scripts/fix_daf_shift.py jsonl  IN.jsonl  OUT.jsonl   # gemara_chunks / corpus_meta rows
    python scripts/fix_daf_shift.py links  IN.jsonl  OUT.jsonl   # link graph edges

`id`/`chunk_id` are left UNCHANGED (opaque stable keys) so the live store and the index
stay in lock-step; only human-/retrieval-facing fields move (ref, anchor_ref, deep_link,
daf/chapter, document header).
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chavruta.corpus.talmud_ref import daf_component, shift_daf  # noqa: E402

DELTA = -1


def _shift_deeplink(url: str) -> str:
    marker = "sefaria.org/"
    if marker not in url:
        return url
    head, ref = url.split(marker, 1)
    return f"{head}{marker}{shift_daf(ref, DELTA)}"


def _shift_doc_header(document: str, old_daf: int, new_daf: int, amud: str) -> str:
    """Fix the daf in the first line only: '… Tractate 3a:1' → '… Tractate 2a:1'."""
    if not document:
        return document
    head, _, rest = document.partition("\n")
    head = head.replace(f"{old_daf}{amud}:", f"{new_daf}{amud}:", 1)
    return head if not rest else f"{head}\n{rest}"


# ── live Qdrant payloads (ABSOLUTE set from the corrected source, idempotent) ──

def _correct_map(fixed_jsonl):
    """chunk_id → (ref, anchor_ref, deep_link, chapter) from the ALREADY-shifted source.

    Absolute (not relative): re-runnable and safe after a partial relative pass, because
    it sets each point to the one correct value keyed by the stable chunk_id."""
    from chavruta.corpus.ingest import payload_from_legacy_meta

    out = {}
    for line in Path(fixed_jsonl).open(encoding="utf-8"):
        line = line.rstrip("\n")
        if not line:
            continue
        pl = payload_from_legacy_meta(json.loads(line))
        out[pl["chunk_id"]] = (pl.get("ref"), pl.get("anchor_ref"),
                               pl.get("deep_link"), pl.get("position") or {})
    return out


def fix_qdrant(fixed_jsonl):
    from qdrant_client import QdrantClient, models
    from chavruta.config.profile import Profile

    p = Profile.from_env()
    url = os.environ.get("CHAVRUTA_QDRANT_URL", p.qdrant_url or "http://localhost:6333")
    coll = os.environ.get("CHAVRUTA_COLLECTION", p.collection)
    correct = _correct_map(fixed_jsonl)
    print(f"[qdrant] {len(correct)} corrected refs loaded from {Path(fixed_jsonl).name}")

    c = QdrantClient(url=url, timeout=600)
    flt = models.Filter(must=[models.FieldCondition(
        key="work_id", match=models.MatchValue(value="talmud_bavli"))])
    total = len(correct)  # exact count() on an unindexed filter times out; map size is the proxy
    print(f"[qdrant] ~{total} talmud points @ {url}/{coll}")

    ops, done, miss, off, t0 = [], 0, 0, None, time.time()
    while True:
        pts, off = c.scroll(coll, scroll_filter=flt, limit=2000, offset=off,
                            with_payload=["chunk_id"], with_vectors=False)
        if not pts:
            break
        for pt in pts:
            cid = (pt.payload or {}).get("chunk_id")
            tgt = correct.get(cid)
            if tgt is None:
                miss += 1
                continue
            ref, anchor, deep, position = tgt
            patch = {"ref": ref, "deep_link": deep, "position": position}
            if anchor:
                patch["anchor_ref"] = anchor
            ops.append(models.SetPayloadOperation(
                set_payload=models.SetPayload(payload=patch, points=[pt.id])))
            done += 1
        for attempt in range(5):                       # idempotent → safe to retry on timeout
            try:
                c.batch_update_points(collection_name=coll, update_operations=ops, wait=True)
                break
            except Exception as e:
                if attempt == 4:
                    raise
                print(f"  retry batch ({type(e).__name__}) …", flush=True)
                time.sleep(3 * (attempt + 1))
        ops = []
        print(f"  {done}/{total}  ({miss} unmatched)  {done/max(time.time()-t0,1e-9):.0f}/s", flush=True)
        if off is None:
            break
    print(f"[qdrant] done {done} relabelled, {miss} unmatched in {time.time()-t0:.0f}s")


# ── JSONL files (gemara_chunks.jsonl, corpus_meta.jsonl) ──────────────────────

def fix_jsonl(inp, outp):
    src, dst = Path(inp), Path(outp)
    n = changed = 0
    with src.open(encoding="utf-8") as fin, dst.open("w", encoding="utf-8") as fout:
        for line in fin:
            line = line.rstrip("\n")
            if not line:
                continue
            rec = json.loads(line)
            md = rec.get("metadata", {})
            if md.get("work") == "talmud_bavli" or (md.get("daf") and md.get("amud")):
                vid = md.get("verse_id", "")
                if daf_component(vid) is not None:
                    old_daf = int(md.get("daf")) if md.get("daf") is not None else None
                    amud = md.get("amud", "")
                    md["verse_id"] = shift_daf(vid, DELTA)
                    if old_daf is not None:
                        md["daf"] = old_daf + DELTA
                        if md.get("chapter") == old_daf:
                            md["chapter"] = old_daf + DELTA
                        rec["document"] = _shift_doc_header(
                            rec.get("document", ""), old_daf, old_daf + DELTA, amud)
                    rec["id"] = rec.get("id", "")  # id left unchanged (opaque key)
                    changed += 1
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    print(f"[jsonl] {src.name}: {changed}/{n} rows shifted → {dst}")


# ── link graph (links.jsonl) ──────────────────────────────────────────────────

def fix_links(inp, outp):
    src, dst = Path(inp), Path(outp)
    n = changed = 0
    with src.open(encoding="utf-8") as fin, dst.open("w", encoding="utf-8") as fout:
        for line in fin:
            line = line.rstrip("\n")
            if not line:
                continue
            rec = json.loads(line)
            touched = False
            for k, v in list(rec.items()):
                if isinstance(v, str) and daf_component(v) is not None:
                    nv = shift_daf(v, DELTA)
                    if nv != v:
                        rec[k] = nv; touched = True
            changed += touched
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    print(f"[links] {src.name}: {changed}/{n} edges shifted → {dst}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "qdrant":
        fix_qdrant(sys.argv[2])
    elif cmd == "jsonl":
        fix_jsonl(sys.argv[2], sys.argv[3])
    elif cmd == "links":
        fix_links(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
        sys.exit(1)
