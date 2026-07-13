# Resume — loading the RAG into local Qdrant

Paused mid-load (needed the machine). State is saved; resume is 2 commands.

## Where we stopped
- **11/14 categories fully loaded** and recorded in `data/processed/local_load.done`:
  second_temple, reference, musar, tosefta, liturgy, kabbalah, midrash, chasidut,
  jewish_thought, shut, tanakh.
- Qdrant had **~1.85M points** (persisted in the Docker volume `qdrant_storage`).
- **Still to load (3):** `mishnah`, `halacha`, `gemara`.
  - mishnah + halacha earlier failed on a transient HTTP reset (WinError 10054) mid-upsert.
    Fixed: `QdrantStore.upsert` now retries with a fresh connection (up to 5×).
  - gemara was interrupted ~340k/711k in — it re-loads fully (upserts are idempotent by
    chunk_id, so the partial rows are just overwritten; nothing to clean up).

## Status 2026-07-04: 13/14 loaded. Only **gemara** left — loading it SLICED.
mishnah + halacha finished (retry fix). gemara (711k) is too big to load in one shot on 16GB
(Qdrant + loader thrash the box), so it loads in fixed 40k-row slices, each in a fresh subprocess
that releases memory, indexing deferred until the end. Memory bug also fixed in
`corpus/ingest.py` (mmap vectors + stream sparse instead of loading all into RAM).
Progress: 3/18 slices done (`data/processed/gemara_slices.done`), ~120k of gemara in.

## To resume gemara (overnight — ~2.5h, resumable)
```powershell
powercfg /change standby-timeout-ac 0        # keep awake (already set)
docker compose up -d qdrant                  # if Qdrant was stopped
python scripts/load_gemara_sliced.py         # continues from the next slice; rebuilds index at end
```
Re-run it any time it stops — the `.done` file skips finished slices. When it prints
"collection now ~2,887,000 points", all 14 categories are in.
Then verify: `python scripts/test_rag.py --no-ask`  (retrieval), or full `test_rag.py` (with Nebius).

Restore sleep when fully done: `powercfg /change standby-timeout-ac 30`

## After all 14 are in (~2.9M points) — run the app (local retrieval + Nebius LLM)
`.env` is already set to local (Qdrant server + bge-m3 CPU) with the LLM on Nebius.
```powershell
docker compose up -d           # api + web + qdrant
# open http://localhost:5173
```
Memory tier `16gb` (int8 quantization + on-disk) keeps RAM ~4GB. See `store.MEM_TIERS`
for `32gb` / `max` tiers on bigger machines.
