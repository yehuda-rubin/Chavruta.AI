"""Extract dataset for training custom Chavruta Reranker.

This script:
1. Connects to SQLite chat database via app.db.
2. Finds user questions paired with assistant responses that have grounded citations.
3. Runs hybrid retrieval (or vector retrieval) against Qdrant for top_k=16 candidate passages.
4. Matches retrieved passages against assistant citations to create binary labels (1=cited, 0=uncited).
5. Exports training pairs (query, passage_text, label, ref) to JSONL format for Kaggle / Colab fine-tuning.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import app.db as db  # noqa: E402
from chavruta.corpus.schema import Query  # noqa: E402
from chavruta.retrieval.hybrid import HybridRetriever  # noqa: E402


def _normalize_ref(ref: str) -> str:
    """Normalize reference string for matching (strip whitespace, lowercase, underscores)."""
    if not ref:
        return ""
    return ref.strip().lower().replace(" ", "_").replace(".", "_")


def _extract_cited_refs(citations_json: str | list | dict) -> set[str]:
    """Parse citations JSON and extract set of normalized reference strings."""
    if not citations_json:
        return set()
    if isinstance(citations_json, str):
        try:
            citations_json = json.loads(citations_json)
        except Exception:
            return set()
    
    refs = set()
    if isinstance(citations_json, list):
        for item in citations_json:
            if isinstance(item, str):
                refs.add(_normalize_ref(item))
            elif isinstance(item, dict):
                ref = item.get("ref") or item.get("reference") or item.get("chunk_id", "")
                if ref:
                    refs.add(_normalize_ref(ref))
    elif isinstance(citations_json, dict):
        for key in ("refs", "citations", "items"):
            if key in citations_json and isinstance(citations_json[key], list):
                for item in citations_json[key]:
                    if isinstance(item, str):
                        refs.add(_normalize_ref(item))
                    elif isinstance(item, dict) and "ref" in item:
                        refs.add(_normalize_ref(item["ref"]))
    return refs


def fetch_question_citation_pairs(conn: sqlite3.Connection) -> list[dict]:
    """Fetch user questions paired with assistant citations from SQLite DB."""
    query = """
    SELECT 
        u.id as user_msg_id,
        u.text as question,
        u.intent as intent,
        a.id as assistant_msg_id,
        a.citations as citations,
        a.text as answer
    FROM messages u
    JOIN messages a ON u.session_id = a.session_id AND a.role = 'assistant'
    WHERE u.role = 'user'
      AND a.citations IS NOT NULL 
      AND a.citations != '[]'
      AND a.citations != ''
    ORDER BY u.id DESC
    """
    cursor = conn.cursor()
    cursor.execute(query)
    rows = cursor.fetchall()
    
    results = []
    for r in rows:
        cited_refs = _extract_cited_refs(r[4])
        if cited_refs:
            results.append({
                "user_msg_id": r[0],
                "question": r[1],
                "intent": r[2] or "qa",
                "assistant_msg_id": r[3],
                "cited_refs": list(cited_refs),
            })
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="eval/reranker_training_dataset.jsonl", help="Output JSONL path")
    parser.add_argument("--top-k", type=int, default=16, help="Top K candidates to retrieve per question")
    parser.add_argument("--limit", type=int, default=1000, help="Max questions to process")
    args = parser.parse_args()

    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print("Connecting to SQLite database...")
    conn = db.get_conn()
    pairs = fetch_question_citation_pairs(conn)
    print(f"Found {len(pairs)} questions with non-empty citations.")

    if not pairs:
        print("No training questions with citations found in DB.")
        return 0

    print("Initializing HybridRetriever...")
    try:
        from chavruta.config.profile import Profile
        from chavruta.pipeline.pipeline import build_backends

        profile = Profile.from_env()
        _, _, _, retriever = build_backends(profile)
    except Exception as err:
        print(f"Error initializing HybridRetriever: {err}")
        print("Make sure Qdrant is running or configured properly.")
        return 1

    dataset = []
    total_positives = 0
    total_negatives = 0

    for idx, item in enumerate(pairs[:args.limit]):
        question_text = item["question"]
        cited_refs = set(item["cited_refs"])

        q = Query(text=question_text, intent=item["intent"])
        try:
            res = retriever.retrieve(q, top_k=args.top_k)
        except Exception as err:
            print(f"[{idx+1}/{len(pairs)}] Retrieval failed for '{question_text[:30]}...': {err}")
            continue

        q_positives = 0
        q_negatives = 0

        for hit in res.hits:
            hit_ref_norm = _normalize_ref(hit.ref)
            chunk_id_norm = _normalize_ref(hit.chunk_id)

            # Match hit ref or chunk id against cited_refs
            is_positive = any(
                ref in hit_ref_norm or hit_ref_norm in ref or ref in chunk_id_norm
                for ref in cited_refs
            )

            label = 1 if is_positive else 0
            if is_positive:
                q_positives += 1
            else:
                q_negatives += 1

            dataset.append({
                "question": question_text,
                "passage": hit.text,
                "ref": hit.ref,
                "chunk_id": hit.chunk_id,
                "label": label,
                "user_msg_id": item["user_msg_id"]
            })

        total_positives += q_positives
        total_negatives += q_negatives

        if (idx + 1) % 50 == 0 or (idx + 1) == len(pairs):
            print(f"Processed {idx+1}/{min(len(pairs), args.limit)} questions | Pairs generated: {len(dataset)} (Pos: {total_positives}, Neg: {total_negatives})")

    with out_path.open("w", encoding="utf-8") as fh:
        for row in dataset:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"\nExtraction complete!")
    print(f"Saved {len(dataset)} pairs ({total_positives} positive, {total_negatives} negative) to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
