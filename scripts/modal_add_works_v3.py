"""modal_add_works_v3.py — add vetted Hebrew works to the commercial index and publish v3, on a B200.

The same shape as modal_full_torah_wikisource_ingest.py (fetch → chunk → embed bge-m3 dense+sparse on a
Modal B200 → merge with the existing index → publish to Hugging Face), for works that Sefaria licenses
for commercial use IN HEBREW. Currently: Sefer HaKuzari (Project Ben-Yehuda edition, CC-BY-SA).

It never touches the live collection and never overwrites v2: it writes a NEW dataset repo
(`chavruta-commercial-v3-index`) holding
    corpus_vectors.npy / corpus_sparse.jsonl / corpus_meta.jsonl     the merged index: v2 + new works,
                                                                       minus the Tanya chunks removed
                                                                       from production on 2026-10-xx
    additions/                                                         ONLY the new works, same three files,
                                                                       for an incremental load into Qdrant
Loading into the live collection is a separate, explicit step (see docs/TODO_AFTER_DAFYOMI_2026-10.md).

    python -m modal run scripts/modal_add_works_v3.py
"""
from __future__ import annotations

import os

try:
    import modal
except ImportError:  # the file stays importable (tests, linting) without the modal client
    modal = None

# Each work: Sefaria title, the exact Hebrew version title (its licence is checked at run time), and the
# metadata the live corpus carries for comparable works (see Duties of the Heart / Sefat Emet payloads).
WORKS = [
    dict(title="Kuzari", version="Sefer haKuzari - Project Ben-Yehuda", display_en="Kuzari", author_he="הכוזרי",
         tag_he="הכוזרי", chunk_type="jewish_thought", category_path="Jewish Thought",
         allowed_licenses=("CC-BY-SA", "Public Domain", "CC0", "CC-BY")),
]

TANYA_IDS_FILE = "eval_results/tanya_removed_backup.json"

if modal is not None:
    app = modal.App("chavruta-add-works-v3")
    image = (
        modal.Image.debian_slim(python_version="3.11")
        .pip_install("torch", "numpy", "FlagEmbedding", "huggingface_hub", "requests", "tqdm")
        .add_local_file(TANYA_IDS_FILE, "/root/tanya_removed_backup.json")
    )

    @app.function(gpu="b200", image=image, timeout=7200, memory=98304, cpu=16)
    def run(base_repo: str = "Yehuda-Rubin/chavruta-commercial-v2-index",
            target_repo: str = "Yehuda-Rubin/chavruta-commercial-v3-index", hf_token: str = ""):
        import json
        import re
        import time
        import urllib.parse
        import urllib.request
        from pathlib import Path

        import numpy as np
        import torch
        from FlagEmbedding import BGEM3FlagModel
        from huggingface_hub import HfApi, create_repo, hf_hub_download

        token = hf_token or os.environ.get("HF_TOKEN")
        api = HfApi(token=token)
        print("GPU:", torch.cuda.get_device_name(0))
        work_dir = Path("/tmp/v3")
        work_dir.mkdir(parents=True, exist_ok=True)

        # ---- 1. fetch the works from Sefaria, licence checked per version ---------------------------
        def get(url):
            req = urllib.request.Request(url, headers={"User-Agent": "ChavrutaBot/1.0 (https://chavrutaai.org)"})
            return json.load(urllib.request.urlopen(req, timeout=120))

        niqqud = re.compile(r"[֑-ׇ]")
        new = []                                         # {"id","embed_text","meta"}
        for w in WORKS:
            vers = get(f"https://www.sefaria.org/api/texts/versions/{urllib.parse.quote(w['title'])}")
            match = [v for v in vers if v.get("language") == "he" and v.get("versionTitle") == w["version"]]
            if not match or match[0].get("license") not in w["allowed_licenses"]:
                raise SystemExit(f"REFUSING {w['title']}: version/licence not as expected: {match}")
            lic = match[0]["license"]
            idx = get(f"https://www.sefaria.org/api/v2/index/{urllib.parse.quote(w['title'])}")
            n_sec = idx["schema"]["lengths"][0]
            print(f"{w['title']}: {lic}, {n_sec} top-level sections")
            for s in range(1, n_sec + 1):
                r = get("https://www.sefaria.org/api/v3/texts/"
                        f"{urllib.parse.quote(w['title'])}.{s}?version=hebrew%7C{urllib.parse.quote(w['version'])}")
                text = r["versions"][0]["text"]
                for k, line in enumerate(text, 1):
                    line = re.sub(r"<[^>]+>", "", line or "").strip()
                    if not line:
                        continue
                    verse_id = f"{w['title']}.{s}.{k}"
                    human = f"{w['display_en']} {s}:{k}"
                    new.append({
                        "id": f"{verse_id}_{w['chunk_type']}",
                        # recall: dense/sparse are computed on the niqqud-stripped text (see niqqud-recall-gap);
                        # the stored text keeps the vocalised original for display.
                        "embed_text": f"[{w['tag_he']}] {human}\n{niqqud.sub('', line)}",
                        "meta": {
                            "verse_id": verse_id, "ref": human, "book": w["display_en"], "chapter": s, "verse": k,
                            "chunk_type": w["chunk_type"], "commentator": "", "work": w["chunk_type"],
                            "period": w["chunk_type"], "author_he": w["author_he"], "section": f"Essay {s}",
                            "category_path": w["category_path"], "text_he": line, "text_en": "",
                            "license_he": lic, "version_he": w["version"], "license_en": "", "version_en": "",
                        },
                        "document": f"[{w['tag_he']}] {human}\n{line}",
                    })
        print(f"new chunks: {len(new)}")
        assert new, "nothing fetched"

        # ---- 2. embed on the B200 (dense normalised + sparse lexical weights) ------------------------
        model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True, device="cuda")
        enc = model.encode([c["embed_text"] for c in new], batch_size=256, max_length=512,
                           return_dense=True, return_sparse=True, return_colbert_vecs=False)
        dense = np.asarray(enc["dense_vecs"], dtype="float32")
        dense /= np.where((n := np.linalg.norm(dense, axis=1, keepdims=True)) == 0, 1.0, n)
        sparse = [{int(t): float(v) for t, v in dict(x).items()} for x in enc["lexical_weights"]]

        # ---- 3. merge with v2, dropping Tanya -------------------------------------------------------
        tanya_ids = {p["payload"]["chunk_id"] for p in json.load(open("/root/tanya_removed_backup.json", encoding="utf-8"))}
        tanya_re = re.compile(r"תניא|tanya", re.I)
        files = {n: hf_hub_download(repo_id=base_repo, filename=n, repo_type="dataset", token=token)
                 for n in ("corpus_vectors.npy", "corpus_sparse.jsonl", "corpus_meta.jsonl")}
        old_vecs = np.load(files["corpus_vectors.npy"], mmap_mode="r")
        print("base points:", old_vecs.shape[0])

        keep, drop_rows, seen_ids = [], [], set()
        out_meta = work_dir / "corpus_meta.jsonl"
        with open(files["corpus_meta.jsonl"], encoding="utf-8") as fin, open(out_meta, "w", encoding="utf-8") as fout:
            for rn, line in enumerate(fin):
                rec = json.loads(line)
                if rec["id"] in tanya_ids or tanya_re.search(rec["id"]) or tanya_re.search((rec.get("metadata") or {}).get("ref", "")):
                    drop_rows.append(rn)
                    continue
                seen_ids.add(rec["id"])
                rec["i"] = len(keep)
                keep.append(rec["i"])
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            clash = [c["id"] for c in new if c["id"] in seen_ids]
            assert not clash, f"ids already in v2: {clash[:3]}"
            base_n = len(keep)
            for j, c in enumerate(new):
                fout.write(json.dumps({"i": base_n + j, "id": c["id"], "document": c["document"], "metadata": c["meta"]},
                                      ensure_ascii=False) + "\n")
        dropped = len(drop_rows)
        print(f"dropped Tanya rows: {dropped}; kept {base_n}; added {len(new)}")
        assert dropped > 0, "expected to drop the Tanya rows from v2"
        merged = np.concatenate([np.delete(np.asarray(old_vecs), drop_rows, axis=0), dense], axis=0)
        assert merged.shape[0] == base_n + len(new)
        np.save(work_dir / "corpus_vectors.npy", merged)

        drop_set = set(drop_rows)
        out_sparse = work_dir / "corpus_sparse.jsonl"
        with open(files["corpus_sparse.jsonl"], encoding="utf-8") as fin, open(out_sparse, "w", encoding="utf-8") as fout:
            n_out = 0
            for rn, line in enumerate(fin):
                if rn in drop_set:
                    continue
                row = json.loads(line)
                row["i"] = n_out
                fout.write(json.dumps(row) + "\n")
                n_out += 1
            for j, sp in enumerate(sparse):
                fout.write(json.dumps({"i": base_n + j, "sparse": sp}) + "\n")
        assert n_out == base_n, (n_out, base_n)

        # ---- 4. additions-only files (for an incremental load) --------------------------------------
        add_dir = work_dir / "additions"
        add_dir.mkdir(exist_ok=True)
        np.save(add_dir / "corpus_vectors.npy", dense)
        with open(add_dir / "corpus_sparse.jsonl", "w") as f:
            for j, sp in enumerate(sparse):
                f.write(json.dumps({"i": j, "sparse": sp}) + "\n")
        with open(add_dir / "corpus_meta.jsonl", "w", encoding="utf-8") as f:
            for j, c in enumerate(new):
                f.write(json.dumps({"i": j, "id": c["id"], "document": c["document"], "metadata": c["meta"]},
                                   ensure_ascii=False) + "\n")

        # ---- 5. publish a NEW repo (v2 untouched) ---------------------------------------------------
        create_repo(target_repo, repo_type="dataset", exist_ok=True, token=token)
        for p in [add_dir / n for n in ("corpus_vectors.npy", "corpus_sparse.jsonl", "corpus_meta.jsonl")]:
            api.upload_file(path_or_fileobj=str(p), path_in_repo=f"additions/{p.name}", repo_id=target_repo, repo_type="dataset")
        for p in [work_dir / n for n in ("corpus_meta.jsonl", "corpus_sparse.jsonl", "corpus_vectors.npy")]:
            print(f"uploading {p.name} ({p.stat().st_size / 1e6:.0f} MB)")
            api.upload_file(path_or_fileobj=str(p), path_in_repo=p.name, repo_id=target_repo, repo_type="dataset")
        readme = (f"# chavruta-commercial-v3-index\n\n{base_n + len(new):,} points = v2 minus {dropped} Tanya chunks "
                  f"plus {len(new)} new chunks ({', '.join(w['title'] for w in WORKS)}). Embedded with BAAI/bge-m3 on a B200. "
                  "`additions/` holds only the new works for an incremental load. All texts PD/CC0/CC-BY/CC-BY-SA.\n")
        api.upload_file(path_or_fileobj=readme.encode(), path_in_repo="README.md", repo_id=target_repo, repo_type="dataset")
        print("DONE", base_n + len(new), "points ->", target_repo)

    @app.local_entrypoint()
    def main():
        from dotenv import dotenv_values
        tok = os.environ.get("HF_TOKEN") or dotenv_values(".env").get("HF_TOKEN") or ""
        print("launching on a Modal B200 (no secrets printed)")
        run.remote(hf_token=tok)
