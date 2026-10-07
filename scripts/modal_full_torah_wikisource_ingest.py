"""modal_full_torah_wikisource_ingest.py — Massive ingestion of the ENTIRE legitimate
Hebrew Wikisource rabbinic/Torah bookshelf, filtered against existing Chavruta corpus
and non-kosher genres (Haskalah, Apocrypha, secular poetry/laws), embedded on NVIDIA B200.

Usage:
  python -m modal run scripts/modal_full_torah_wikisource_ingest.py
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    import modal
except ImportError:
    modal = None

if modal is not None:
    app = modal.App("chavruta-full-wikisource-b200")

    # Container definition with fast dependencies and local title catalog
    image = (
        modal.Image.debian_slim(python_version="3.11")
        .pip_install(
            "torch",
            "numpy",
            "FlagEmbedding",
            "huggingface_hub",
            "requests",
            "tqdm",
        )
        .add_local_file("src/chavruta/corpus/data/hebrew_titles.json", "/root/hebrew_titles.json")
    )

    @app.function(
        gpu="b200",  # NVIDIA B200 GPU (192GB HBM3e)
        image=image,
        timeout=7200,  # up to 2 hours
        memory=65536,  # 64 GB RAM
        cpu=16,
    )
    def run_full_torah_ingest(
        base_index_repo: str = "Yehuda-Rubin/chavruta-commercial-index",
        target_index_repo: str = "Yehuda-Rubin/chavruta-commercial-v2-index",
        target_chunks_repo: str = "Yehuda-Rubin/chavruta-wikisource-additions",
        hf_token: str = "",
        batch_size: int = 4096,
    ):
        import bz2
        import json
        import re
        import shutil
        import time
        import urllib.request
        import xml.etree.ElementTree as ET
        import numpy as np
        import torch
        from FlagEmbedding import BGEM3FlagModel
        from huggingface_hub import HfApi, create_repo, hf_hub_download

        token = hf_token or os.environ.get("HF_TOKEN")
        print("=== Full Hebrew Wikisource Torah Ingestion on NVIDIA B200 ===")
        print(f"Device: {torch.cuda.get_device_name(0)}")
        print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / (1024**3):.1f} GB")

        work_dir = Path("/tmp/full_wikisource")
        work_dir.mkdir(parents=True, exist_ok=True)
        dump_path = work_dir / "hewikisource-latest-pages-articles.xml.bz2"

        # ----------------------------------------------------------------------
        # 1. Download Official Wikimedia Dump (433 MB)
        # ----------------------------------------------------------------------
        dump_url = "https://dumps.wikimedia.org/hewikisource/latest/hewikisource-latest-pages-articles.xml.bz2"
        print(f"\n[1/6] Downloading official Wikisource dump from {dump_url}...")
        t0 = time.time()
        req = urllib.request.Request(dump_url, headers={"User-Agent": "ChavrutaBot/1.0 (https://chavrutaai.org; contact@chavrutaai.org)"})
        with urllib.request.urlopen(req) as resp, open(dump_path, "wb") as out_f:
            shutil.copyfileobj(resp, out_f)
        print(f"Downloaded dump: {dump_path.stat().st_size / (1024**2):.1f} MB in {time.time()-t0:.1f}s")

        # ----------------------------------------------------------------------
        # 2. Setup Whitelist, Blacklist, and Chavruta Deduplication
        # ----------------------------------------------------------------------
        print("\n[2/6] Initializing Rabbinic Canon filters and Chavruta title deduplication...")

        # Load Chavruta existing titles
        def normalize_title(title: str) -> str:
            if not title: return ""
            t = re.sub(r"\.(?:txt|json|csv)$", "", title, flags=re.IGNORECASE)
            t = re.sub(r"[\u0591-\u05C7]", "", t)
            t = re.sub(r"[\'\"״״׳\-\–—\(\)\[\]\.,]", "", t)
            t = re.sub(r"^(ספר|קונטרס|פירוש|ביאור|על|מסכת)\s+", "", t.strip())
            t = re.sub(r"\s+", " ", t).strip()
            return t.lower()

        existing_titles = set()
        with open("/root/hebrew_titles.json", "r", encoding="utf-8") as f:
            hdata = json.load(f)
            for en, inf in hdata.items():
                if en: existing_titles.add(normalize_title(en))
                he = inf.get("he", "")
                if he:
                    existing_titles.add(normalize_title(he))
                    if " על " in he:
                        existing_titles.add(normalize_title(he.split(" על ", 1)[1]))
        print(f"Loaded {len(existing_titles):,} normalized titles from Chavruta core index.")

        # Keywords that confirm legitimate Torah content
        KOSHER_KEYWORDS = [
            "ארון הספרים היהודי", "תורה", "משנה", "גמרא", "תלמוד", "הלכה", "שו\"ת",
            "שאלות ותשובות", "ראשונים", "אחרונים", "מוסר", "מחשבת ישראל", "חסידות",
            "קבלה", "מדרש", "פרשנות", "פוסקים", "נושאי כלים", "ספרות תורנית", "רמב\"ם",
            "רש\"י", "תוספות", "שולחן ערוך", "גאונים", "ספרי קודש", "ליטורגיה",
            "סדר התפילה", "ברכות", "מצוות", "טעמי המקרא", "חידושי", "דרשות",
        ]

        # Keywords that REJECT modern secular, state laws, haskalah, apocrypha
        PROHIBITED_KEYWORDS = [
            "חוק", "חוק-יסוד", "פקודה", "תקנות", "פסק דין", "ספר החוקים", "הכנסת",
            "ספרים חיצוניים", "מגילות ים המלח", "חנוך", "יובלות", "בן סירא", "צוואות השבטים",
            "מקבים", "עזרא הרביעי", "אפוקריפה", "השכלה", "תנועת ההשכלה", "ספרי השכלה",
            "משכילים", "מנדלסון", "נפתלי הרץ וייזל", "שלמה מימון", "יל\"ג", "מאפו",
            "ספרות עברית", "שירה עברית", "שירים", "פזמונים", "סיפורת", "רומנים",
            "ביאליק", "טשרניחובסקי", "רחל", "ברנר", "אחד העם", "עגנון", "שלונסקי", "אלתרמן",
            "מחקר המקרא", "ביקורת המקרא", "ביקורת הנוסח", "מחקר אקדמי", "קראים",
            "יהדות קראית", "רפורמים", "יהדות רפורמית", "קונסרבטיבים", "שומרונים",
            "בשמים ראש", "נצרות", "ברית חדשה", "אסלאם", "קוראן", "עיתונות",
        ]

        def clean_wikitext(text: str) -> str:
            if not text: return ""
            text = re.sub(r"<noinclude>.*?</noinclude>", "", text, flags=re.DOTALL)
            text = re.sub(r"</?includeonly>", "", text)
            text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
            text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.DOTALL)
            text = re.sub(r"<ref[^>]*/>", "", text)
            text = re.sub(r"\{\|.*?\|\}", "", text, flags=re.DOTALL)
            for _ in range(3):
                text = re.sub(r"\{\{[^{}]*\}\}", "", text)
            text = re.sub(r"\[\[(?:קטגוריה|Category|קובץ|File|תמונה|Image):[^\]]+\]\]", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", text)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"'{2,5}", "", text)
            text = re.sub(r"^=+\s*([^=]+?)\s*=+.*$", r"\1", text, flags=re.MULTILINE)
            text = re.sub(r"^[ \t]*[:*#]+[ \t]*", "", text, flags=re.MULTILINE)
            text = re.sub(r"[ \t]+", " ", text)
            text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
            return text.strip()

        def split_into_chunks(text: str, title: str, layer: str, deep_link: str) -> list[dict]:
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
            chunks = []
            cur_doc = []
            cur_len = 0

            clean_slug = re.sub(r"[^a-zA-Z0-9\u0590-\u05FF]+", "_", title)

            for p in paragraphs:
                w_count = len(p.split())
                if cur_len + w_count > 300 and cur_doc:
                    doc_text = "\n\n".join(cur_doc)
                    chunk_idx = len(chunks) + 1
                    ref = f"{title}, אות {chunk_idx}" if len(paragraphs) > 1 else title
                    chunk_id = f"ws:{layer}:{clean_slug}_{chunk_idx}"
                    chunks.append({
                        "id": chunk_id,
                        "document": doc_text,
                        "metadata": {
                            "ref": ref,
                            "book": title,
                            "work_id": layer,
                            "license": "CC-BY-SA 4.0",
                            "deep_link": deep_link,
                            "unit_type": "source",
                        }
                    })
                    cur_doc = [p]
                    cur_len = w_count
                else:
                    cur_doc.append(p)
                    cur_len += w_count

            if cur_doc:
                doc_text = "\n\n".join(cur_doc)
                chunk_idx = len(chunks) + 1
                ref = f"{title}, אות {chunk_idx}" if len(chunks) > 0 else title
                chunk_id = f"ws:{layer}:{clean_slug}_{chunk_idx}"
                chunks.append({
                    "id": chunk_id,
                    "document": doc_text,
                    "metadata": {
                        "ref": ref,
                        "book": title,
                        "work_id": layer,
                        "license": "CC-BY-SA 4.0",
                        "deep_link": deep_link,
                        "unit_type": "source",
                    }
                })
            return chunks

        # ----------------------------------------------------------------------
        # 3. Stream XML Dump & Extract Legitimate Torah Chunks
        # ----------------------------------------------------------------------
        print("\n[3/6] Streaming XML dump and filtering Torah texts...")
        new_chunks = []
        total_articles_scanned = 0
        skipped_existing = 0
        skipped_prohibited = 0
        accepted_pages = 0

        t_scan = time.time()
        with bz2.open(dump_path, "rt", encoding="utf-8") as f:
            for _, elem in ET.iterparse(f, events=("end",)):
                if elem.tag.endswith("page"):
                    ns = elem.findtext("{*}ns")
                    title = elem.findtext("{*}title")

                    if ns == "0" and title:
                        total_articles_scanned += 1
                        raw_text = elem.findtext(".//{*}text") or ""

                        # Skip redirects, disambiguation, empty
                        if "#הפניה" in raw_text or "#REDIRECT" in raw_text or "{{פירושונים}}" in raw_text or len(raw_text) < 100:
                            elem.clear()
                            continue

                        # Extract categories
                        cats = re.findall(r"\[\[(?:קטגוריה|Category):([^\]|]+)", raw_text, flags=re.IGNORECASE)
                        cat_str = " ".join(cats)
                        title_clean = title.replace("_", " ")

                        # Check prohibited
                        full_label = f"{title_clean} {cat_str}"
                        if any(bad in full_label for bad in PROHIBITED_KEYWORDS):
                            skipped_prohibited += 1
                            elem.clear()
                            continue

                        # Check kosher
                        if not any(k in full_label for k in KOSHER_KEYWORDS):
                            elem.clear()
                            continue

                        # Check existing in Chavruta
                        root_title = title_clean.split("/")[0]
                        norm_root = normalize_title(root_title)
                        if norm_root in existing_titles:
                            skipped_existing += 1
                            elem.clear()
                            continue

                        # Determine layer
                        layer = "jewish_thought"
                        if any(w in full_label for w in ["הלכה", "שולחן ערוך", "מנהג", "פסקי"]):
                            layer = "halacha"
                        elif any(w in full_label for w in ["שו\"ת", "שאלות ותשובות", "תשובות"]):
                            layer = "responsa"
                        elif any(w in full_label for w in ["מוסר"]):
                            layer = "musar"
                        elif any(w in full_label for w in ["חסידות"]):
                            layer = "chasidut"
                        elif any(w in full_label for w in ["קבלה", "נסתר", "זוהר"]):
                            layer = "kabbalah"
                        elif any(w in full_label for w in ["מדרש"]):
                            layer = "midrash"
                        elif any(w in full_label for w in ["גמרא", "תלמוד", "ש\"ס", "בבלי", "ירושלמי"]):
                            layer = "talmud_bavli"
                        elif any(w in full_label for w in ["משנה"]):
                            layer = "mishnah"

                        clean_content = clean_wikitext(raw_text)
                        if len(clean_content) < 80:
                            elem.clear()
                            continue

                        deep_link = f"https://he.wikisource.org/wiki/{urllib.request.quote(title.replace(' ', '_'))}"
                        page_chunks = split_into_chunks(clean_content, title_clean, layer, deep_link)
                        new_chunks.extend(page_chunks)
                        accepted_pages += 1

                        if accepted_pages % 500 == 0:
                            print(f"  📖 Accepted {accepted_pages:,} pages -> {len(new_chunks):,} chunks so far (scanned {total_articles_scanned:,})")

                    elem.clear()

        print("\n" + "=" * 60)
        print(f"XML DUMP SCAN COMPLETED in {time.time()-t_scan:.1f}s:")
        print(f"- Total articles scanned: {total_articles_scanned:,}")
        print(f"- Skipped prohibited (secular/haskalah/laws): {skipped_prohibited:,}")
        print(f"- Skipped already in Chavruta: {skipped_existing:,}")
        print(f"- Approved brand-new Torah pages: {accepted_pages:,}")
        print(f"- Total Semantic RAG Chunks Generated: {len(new_chunks):,}")
        print("=" * 60)

        # Save new chunks to file and upload to HF dataset
        chunks_jsonl_path = work_dir / "wikisource_full_torah_chunks.jsonl"
        with open(chunks_jsonl_path, "w", encoding="utf-8") as out_f:
            for c in new_chunks:
                out_f.write(json.dumps(c, ensure_ascii=False) + "\n")
        print(f"Saved {len(new_chunks):,} chunks to {chunks_jsonl_path} ({chunks_jsonl_path.stat().st_size / (1024**2):.1f} MB)")

        api = HfApi(token=token)
        print(f"Uploading full raw chunks to {target_chunks_repo}...")
        api.upload_file(
            path_or_fileobj=str(chunks_jsonl_path),
            path_in_repo="wikisource_full_torah_chunks.jsonl",
            repo_id=target_chunks_repo,
            repo_type="dataset",
            token=token
        )

        # ----------------------------------------------------------------------
        # 4. GPU Embedding on NVIDIA B200 with BAAI/bge-m3
        # ----------------------------------------------------------------------
        print(f"\n[4/6] Initializing BGE-M3 model on B200 (batch_size={batch_size})...")
        model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True, device="cuda")

        docs = [c["document"] for c in new_chunks]
        dense_parts, sparse_rows = [], []

        t_embed = time.time()
        for s in range(0, len(docs), batch_size):
            batch_docs = docs[s : s + batch_size]
            enc = model.encode(
                batch_docs,
                batch_size=batch_size,
                max_length=512,
                return_dense=True,
                return_sparse=True,
                return_colbert_vecs=False,
            )
            dense_parts.append(np.asarray(enc["dense_vecs"], dtype="float32"))
            for w in enc["lexical_weights"]:
                sparse_rows.append({int(t): float(v) for t, v in dict(w).items()})
            print(f"  🧠 Encoded {min(s + batch_size, len(docs)):,}/{len(docs):,} chunks ({time.time()-t_embed:.1f}s)")

        new_vecs = np.vstack(dense_parts)
        norms = np.linalg.norm(new_vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        new_vecs /= norms
        print(f"All new embeddings ready: {new_vecs.shape[0]:,} vectors ({time.time()-t_embed:.1f}s)")

        # ----------------------------------------------------------------------
        # 5. Download Base Commercial Index & Merge
        # ----------------------------------------------------------------------
        print(f"\n[5/6] Downloading base index from {base_index_repo} and merging...")
        base_vecs_file = hf_hub_download(repo_id=base_index_repo, filename="corpus_vectors.npy", repo_type="dataset", token=token)
        base_sparse_file = hf_hub_download(repo_id=base_index_repo, filename="corpus_sparse.jsonl", repo_type="dataset", token=token)
        base_meta_file = hf_hub_download(repo_id=base_index_repo, filename="corpus_meta.jsonl", repo_type="dataset", token=token)

        old_vecs = np.load(base_vecs_file)
        old_count = old_vecs.shape[0]
        print(f"Base index: {old_count:,} points")

        merged_vecs = np.vstack([old_vecs, new_vecs])
        out_vecs_path = work_dir / "corpus_vectors.npy"
        np.save(str(out_vecs_path), merged_vecs)
        print(f"Merged vector matrix: {merged_vecs.shape[0]:,} points ({out_vecs_path.stat().st_size / (1024**2):.1f} MB)")

        out_sparse_path = work_dir / "corpus_sparse.jsonl"
        with open(base_sparse_file, "r", encoding="utf-8") as in_f, open(out_sparse_path, "w", encoding="utf-8") as out_f:
            for line in in_f:
                out_f.write(line)
            for i, row in enumerate(sparse_rows):
                out_f.write(json.dumps({"i": old_count + i, "sparse": row}) + "\n")

        out_meta_path = work_dir / "corpus_meta.jsonl"
        with open(base_meta_file, "r", encoding="utf-8") as in_f, open(out_meta_path, "w", encoding="utf-8") as out_f:
            for line in in_f:
                out_f.write(line)
            for i, c in enumerate(new_chunks):
                out_f.write(json.dumps({
                    "i": old_count + i,
                    "id": c["id"],
                    "document": c["document"],
                    "metadata": c.get("metadata", {})
                }, ensure_ascii=False) + "\n")

        # ----------------------------------------------------------------------
        # 6. Upload Complete New RAG Index to Hugging Face
        # ----------------------------------------------------------------------
        print(f"\n[6/6] Uploading expanded unified RAG index ({merged_vecs.shape[0]:,} points) to {target_index_repo}...")
        create_repo(target_index_repo, repo_type="dataset", exist_ok=True, token=token)

        for fn in [out_vecs_path, out_sparse_path, out_meta_path]:
            print(f"  Uploading {fn.name} ({fn.stat().st_size / (1024**2):.1f} MB)...")
            api.upload_file(path_or_fileobj=str(fn), path_in_repo=fn.name, repo_id=target_index_repo, repo_type="dataset", token=token)

        readme = f"""---
license: cc-by-sa-4.0
tags:
- qdrant
- rag
- bge-m3
- torah
- wikisource
- chavruta-ai
---

# Chavruta.AI Commercial Index v2 (Full Torah Expansion)

Massively expanded RAG index over the Jewish bookshelf:
- **Base Corpus:** {old_count:,} points across 15 core layers.
- **Wikisource Expansion:** {new_vecs.shape[0]:,} new rabbinic chunks (Gemara commentators, Shulchan Aruch nosei keilim, Responsa libraries, Midrashim, Mussar, Kabbalah, Chasidut).
- **Total Points:** {merged_vecs.shape[0]:,} points.
- **Embedded on:** NVIDIA B200 (192GB HBM3e) using `BAAI/bge-m3` (dense 1024-dim + sparse lexical).
- **License:** 100% Commercial-permissive (PD / CC0 / CC-BY / CC-BY-SA). Strictly filtered against non-kosher / secular literature.
"""
        api.upload_file(
            path_or_fileobj=readme.encode("utf-8"),
            path_in_repo="README.md",
            repo_id=target_index_repo,
            repo_type="dataset",
            token=token
        )

        print(f"\n🎉 ALL STEPS COMPLETE! Expanded RAG index is live at:")
        print(f"https://huggingface.co/datasets/{target_index_repo}")

        # Cleanup container
        shutil.rmtree(work_dir, ignore_errors=True)
        print("Cleaned up container work directory.")


    @app.local_entrypoint()
    def main():
        import huggingface_hub
        hf_token = os.environ.get("HF_TOKEN") or huggingface_hub.get_token() or ""
        print("Launching Full Wikisource Torah Ingestion on NVIDIA B200 via Modal...")
        run_full_torah_ingest.remote(hf_token=hf_token)
