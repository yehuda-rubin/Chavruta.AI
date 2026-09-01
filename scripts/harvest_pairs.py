"""Harvest retrieval ground truth from the corpus itself — no LLM, no cost, CPU only.

WHY THIS EXISTS
---------------
Retrieval was being changed on the evidence of 26 hand-written questions. Three consecutive
retrieval changes measured 52% / 52% / 52%, which at that sample size is indistinguishable from
noise — meaning every constant in the retriever (the tractate boost, the base-text slots, the
prefetch multiplier) is a guess nobody can check. This produces thousands of (query, correct answer)
pairs mechanically, so those constants can be chosen by measurement instead.

WHERE THE LABELS COME FROM
--------------------------
Sefaria names a commentary `<Title>_on_<Base>.<k>` — so `Rashi_on_Sukkah.81.11.2` already tells us,
in the ref string alone, that it comments on `Sukkah.81`. That is a free, exact, human-authored
label: a rabbi wrote an explanation of a specific passage, and the file name records which. There
are ~1.26M such edges in the corpus.

The pair is deliberately (commentary body -> base ref), not the reverse. The commentary RESTATES the
base text in different words, so retrieving the base from the commentary is a real semantic jump —
the same kind of jump a user makes when they ask about a sugya in their own words. Generating a
query out of a chunk's own text and then retrieving that chunk would measure almost nothing: the
answer is a near-copy of the question.

WHAT THIS CANNOT DO — READ BEFORE TRUSTING THE NUMBERS
------------------------------------------------------
These queries are written in rabbinic Hebrew, because they ARE rabbinic Hebrew. Real users write
modern colloquial Hebrew, and that gap is the measured failure: the same chunk ranked #2 for a
source-language query and outside the top 50 for the human phrasing of the same question. So a
retriever tuned to maximise the score here could get WORSE at the thing that actually broke.

That is not a reason to skip this — it is a reason to keep the human-written eval sets as a separate
VETO. scripts/tune_retrieval.py does exactly that: it searches on these pairs and rejects any
setting that improves them at the human sets' expense. Never tune on this file alone.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

try:
    import torch  # noqa: F401,E402 — must precede qdrant_client on Windows (pyarrow DLL order)
except Exception:  # noqa: BLE001
    pass

from chavruta.config.profile import Profile  # noqa: E402
from chavruta.corpus.refs import commentator_from_ref, is_commentary_ref  # noqa: E402
from chavruta.store.qdrant_store import QdrantStore  # noqa: E402

# A commentary chunk shorter than this is usually a fragment ("ומה שכתב", a bare lemma) that names
# no content at all — as a query it can only retrieve noise, and it would depress every score for a
# reason that has nothing to do with the retriever.
_MIN_QUERY_CHARS = 80
# Long commentaries are truncated rather than dropped: the opening of a comment is where it states
# what it is about, and an 8k-character query is not a question anyone would ask.
_MAX_QUERY_CHARS = 600


def _base_ref(ref: str) -> str | None:
    """The base ref a commentary ref comments on: 'Rashi_on_Sukkah.81.11.2' -> 'Sukkah.81.11'.

    Sefaria names a commentary '<Title>_on_<Base>.<k>', where k enumerates the comments on that one
    base segment — so the base is recovered by dropping the LAST numeric component and nothing else.

    Verified against the live collection (2026-08-12) rather than reasoned about, because the first
    version of this was wrong in a way that would have gone unnoticed: it returned the CHAPTER
    ('Sukkah.81', 'Genesis.1'), and since the scorer matches by prefix, every pair would have counted
    any segment in the chapter as correct and the whole eval would have read far better than the
    retriever actually is. The probe settled it — base segments carry two numeric components:

        Sukkah.81.11   exists  |  Sukkah.81   does not
        Genesis.1.1    exists  |  Genesis.1   does not
        Temurah.49.1   exists  |  Temurah.49  does not

    A ref that does not survive that shape is dropped rather than guessed at: a mislabelled pair is
    worse than a missing one, because it silently punishes the retriever for being right.
    """
    if not is_commentary_ref(ref):
        return None
    tail = ref.split("_on_", 1)[1]          # 'Sukkah.81.11.2'
    if "_on_" in tail:                      # supercommentary: Mizrachi_on_Rashi_on_Genesis...
        return None                         # its base is another commentary — not a base-text label
    work, _, coords = tail.partition(".")
    nums = coords.split(".") if coords else []
    if len(nums) < 3 or not all(n.isdigit() for n in nums):
        # Fewer than three means dropping the comment index would not leave a full base segment;
        # a non-numeric coordinate is a shape this rule was never verified against.
        return None
    return f"{work}.{'.'.join(nums[:-1])}"


def harvest(store: QdrantStore, collection: str, *, target: int, per_work_cap: int,
            seed: int, scan_limit: int) -> list[dict]:
    """Scan the collection and emit (commentary text -> base ref) pairs, balanced across works."""
    rng = random.Random(seed)
    per_work: Counter[str] = Counter()
    pairs: list[dict] = []
    scanned = 0
    offset = None

    client = store._client_()
    while scanned < scan_limit and len(pairs) < target:
        points, offset = client.scroll(
            collection_name=collection, limit=2000, offset=offset,
            with_payload=["ref", "text", "text_he", "work_id"], with_vectors=False,
        )
        if not points:
            break
        for p in points:
            scanned += 1
            payload = p.payload or {}
            ref = payload.get("ref") or ""
            base = _base_ref(ref)
            if not base:
                continue
            work = payload.get("work_id") or "?"
            if per_work[work] >= per_work_cap:
                continue
            text = (payload.get("text_he") or payload.get("text") or "").strip()
            if len(text) < _MIN_QUERY_CHARS:
                continue
            per_work[work] += 1
            pairs.append({
                "id": f"hp-{len(pairs) + 1:06d}",
                "question": text[:_MAX_QUERY_CHARS],
                "expected_refs": [base],
                "source_ref": ref,                       # provenance: which comment produced this
                "commentator": commentator_from_ref(ref) or "",
                "work_id": work,
                "generated": "commentary_to_base",
            })
            if len(pairs) >= target:
                break
        if offset is None:
            break

    rng.shuffle(pairs)          # so a train/test split is not a split by corpus order
    return pairs


def verify(store: QdrantStore, collection: str, pairs: list[dict], *, batch: int = 200) -> list[dict]:
    """Drop pairs whose label does not name a real point in the collection.

    Necessary, not belt-and-braces. Measured on a live sample before this existed: only 30 of 40
    derived labels resolved. `_base_ref` assumes Sefaria appends exactly one comment index, which
    holds for most works and not for all — and a label that resolves to nothing is a guaranteed miss
    that drags every candidate setting down by the same amount, adding noise to the very measurement
    this whole eval set exists to make less noisy.

    So the shape is not argued about, it is checked. Anything that fails is dropped rather than
    repaired: a mislabelled pair punishes the retriever for being right, which is worse than a
    smaller set.
    """
    kept: list[dict] = []
    for i in range(0, len(pairs), batch):
        chunk = pairs[i:i + batch]
        refs = [p["expected_refs"][0] for p in chunk]
        try:
            hits = store.fetch_by_refs(collection, refs, limit=len(refs) * 2)
        except Exception:
            continue                      # a failed batch drops that batch, never a bad label
        present = {(h.payload or {}).get("ref") for h in hits}
        kept.extend(p for p in chunk if p["expected_refs"][0] in present)
    return kept


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="eval/harvested_pairs_v1.jsonl")
    ap.add_argument("--target", type=int, default=5000, help="how many pairs to emit")
    ap.add_argument("--per-work-cap", type=int, default=700,
                    help="max pairs from any one work_id — keeps Talmud from swamping the set")
    ap.add_argument("--scan-limit", type=int, default=400_000, help="points to scan at most")
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--no-verify", action="store_true",
                    help="skip checking each label against the collection (faster, but ~25%% of "
                         "the emitted pairs will be unresolvable — see verify())")
    args = ap.parse_args()

    profile = Profile.from_env()
    store = QdrantStore(mode=profile.qdrant_mode, path=profile.qdrant_path,
                        url=profile.qdrant_url, api_key=profile.qdrant_api_key)
    pairs = harvest(store, profile.collection, target=args.target,
                    per_work_cap=args.per_work_cap, seed=args.seed, scan_limit=args.scan_limit)
    if not args.no_verify:
        derived = len(pairs)
        pairs = verify(store, profile.collection, pairs)
        print(f"verified {len(pairs)}/{derived} labels against the collection "
              f"({derived - len(pairs)} dropped as unresolvable)")

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        fh.write("# Chavruta.AI — harvested retrieval pairs (commentary body -> the base text it\n")
        fh.write("# comments on). Generated by scripts/harvest_pairs.py; NOT hand-written.\n")
        fh.write("# These are rabbinic-Hebrew queries. See the module docstring: tuning on this set\n")
        fh.write("# alone can make real (colloquial) questions WORSE. Always keep the human sets as\n")
        fh.write("# a veto — scripts/tune_retrieval.py does.\n")
        for p in pairs:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")

    by_work = Counter(p["work_id"] for p in pairs)
    print(f"wrote {len(pairs)} pairs -> {out}")
    for work, n in by_work.most_common():
        print(f"   {work:<18} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
