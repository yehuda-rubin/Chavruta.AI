# -*- coding: utf-8 -*-
"""Create keyword payload indexes on `ref` and `anchor_ref` for the Qdrant collection.

Without these, link-based retrieval's `fetch_by_refs` scroll filter is a full scan of the whole
collection (~2.75M points) and times out at 60s. A keyword index makes the MatchAny filter indexed
and fast. Safe + idempotent (an existing index is a no-op).

    python scripts/create_payload_indexes.py            # collection from env / default 'chavruta'
"""
import os
import sys

from qdrant_client import QdrantClient
from qdrant_client.http import models

URL = os.environ.get("CHAVRUTA_QDRANT_URL", "http://localhost:6333")
COLLECTION = os.environ.get("CHAVRUTA_COLLECTION", "chavruta")
FIELDS = ("ref", "anchor_ref")


def main() -> None:
    client = QdrantClient(url=URL, timeout=120)
    print(f"collection: {COLLECTION} @ {URL}")
    for field in FIELDS:
        try:
            client.create_payload_index(
                collection_name=COLLECTION,
                field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD,
                wait=True,
            )
            print(f"  ✓ index created on '{field}'")
        except Exception as exc:                       # already exists / transient → report, continue
            print(f"  • '{field}': {exc}")
    info = client.get_collection(COLLECTION)
    print("payload schema now:", sorted((info.payload_schema or {}).keys()))


if __name__ == "__main__":
    sys.exit(main())
