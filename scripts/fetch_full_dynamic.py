# -*- coding: utf-8 -*-
"""fetch_full_dynamic.py — re-fetch Tanakh / Gemara / Mishnah from Sefaria with **every**
commentary, discovered dynamically (not a hardcoded list), and replace the files on HF.

Why: the old fetch_* scripts pulled only a fixed handful of meforshim, so most of Sefaria's
commentaries were missing. Here, for each base text we ask Sefaria's links API which works are
linked as `Commentary` (and optionally `Quoting Commentary`) and fetch *all* of them — Penei
Yehoshua, Rashash, Shita Mekubetzet, Rif, Rosh, Kli Yakar, Rabbeinu Bahya, Abarbanel, Malechet
Shlomo, … whatever Sefaria has. The result overwrites the existing HF file for that domain.

Per the user: ignore the existing data — build each domain fresh, then upload it in place.

Output (matches the names the notebook's EXTRA_SOURCES expects):
    tanakh  → all_chunks_full.json   (JSON object {metadata, chunks})
    gemara  → gemara_chunks.jsonl    (JSONL)
    mishnah → mishnah_chunks.json    (JSON object)

Resumable: a working JSONL + a .done set of finished base texts; re-run to continue.

Run:
    python scripts/fetch_full_dynamic.py --domain mishnah   # one domain
    python scripts/fetch_full_dynamic.py --domain all       # tanakh, gemara, mishnah
    python scripts/fetch_full_dynamic.py --domain gemara --no-upload   # build only, don't push
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

import requests

BASE = "https://www.sefaria.org"
HEADERS = {"User-Agent": "Chavruta.AI/0.2 (educational Torah RAG)"}
HF_REPO = "Yehuda-Rubin/chavruta-torah-mixed"
PROC = Path("data/processed")

_session = requests.Session()
_session.headers.update(HEADERS)

# ── base texts per domain ─────────────────────────────────────────────────────

TANAKH_BOOKS = [
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy",
    "Joshua", "Judges", "I Samuel", "II Samuel", "I Kings", "II Kings",
    "Isaiah", "Jeremiah", "Ezekiel", "Hosea", "Joel", "Amos", "Obadiah", "Jonah",
    "Micah", "Nahum", "Habakkuk", "Zephaniah", "Haggai", "Zechariah", "Malachi",
    "Psalms", "Proverbs", "Job", "Song of Songs", "Ruth", "Lamentations",
    "Ecclesiastes", "Esther", "Daniel", "Ezra", "Nehemiah",
    "I Chronicles", "II Chronicles",
]

GEMARA_TRACTATES = [
    "Berakhot", "Shabbat", "Eruvin", "Pesachim", "Yoma", "Sukkah", "Beitzah",
    "Rosh Hashanah", "Taanit", "Megillah", "Moed Katan", "Chagigah",
    "Yevamot", "Ketubot", "Nedarim", "Nazir", "Sotah", "Gittin", "Kiddushin",
    "Bava Kamma", "Bava Metzia", "Bava Batra", "Sanhedrin", "Makkot", "Shevuot",
    "Avodah Zarah", "Horayot", "Zevachim", "Menachot", "Chullin", "Bekhorot",
    "Arakhin", "Temurah", "Keritot", "Meilah", "Tamid", "Niddah",
]

MISHNAH_TRACTATES = [
    "Berakhot", "Peah", "Demai", "Kilayim", "Sheviit", "Terumot", "Maasrot",
    "Maaser Sheni", "Challah", "Orlah", "Bikkurim",
    "Shabbat", "Eruvin", "Pesachim", "Shekalim", "Yoma", "Sukkah", "Beitzah",
    "Rosh Hashanah", "Taanit", "Megillah", "Moed Katan", "Chagigah",
    "Yevamot", "Ketubot", "Nedarim", "Nazir", "Sotah", "Gittin", "Kiddushin",
    "Bava Kamma", "Bava Metzia", "Bava Batra", "Sanhedrin", "Makkot", "Shevuot",
    "Eduyot", "Avodah Zarah", "Pirkei Avot", "Horayot",
    "Zevachim", "Menachot", "Chullin", "Bekhorot", "Arakhin", "Temurah",
    "Keritot", "Meilah", "Tamid", "Middot", "Kinnim",
    "Kelim", "Oholot", "Negaim", "Parah", "Tahorot", "Mikvaot", "Niddah",
    "Makhshirin", "Zavim", "Tevul Yom", "Yadayim", "Uktzin",
]

# domain → (base_title_fn, output_filename, output_is_jsonl, work_tag)
DOMAINS = {
    "tanakh":  (lambda t: t,                "all_chunks_full.json", False, "tanakh"),
    "gemara":  (lambda t: t,                "gemara_chunks.jsonl",  True,  "talmud_bavli"),
    "mishnah": (lambda t: f"Mishnah {t}",   "mishnah_chunks.json",  False, "mishnah"),
}
DOMAIN_BASES = {"tanakh": TANAKH_BOOKS, "gemara": GEMARA_TRACTATES, "mishnah": MISHNAH_TRACTATES}

# ── Sefaria API ───────────────────────────────────────────────────────────────


def _get(url, params=None, retries=4):
    for attempt in range(retries):
        try:
            r = _session.get(url, params=params, timeout=120)
        except requests.RequestException:
            time.sleep(2 * (attempt + 1)); continue
        if r.status_code == 404:
            return None
        if r.status_code == 200:
            return r
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(3 * (attempt + 1)); continue
        return None
    return None


def fetch_text(ref):
    """GET /api/v3/texts/<ref> → (he_nested, en_nested) or None."""
    r = _get(f"{BASE}/api/v3/texts/{ref}",
             params={"version": ["hebrew", "english"], "return_format": "text_only"})
    if not r:
        return None
    he = en = None
    for v in r.json().get("versions", []):
        fam = (v.get("languageFamilyName") or v.get("language") or "").lower()
        if fam.startswith("he") and he is None:
            he = v.get("text")
        elif fam.startswith("en") and en is None:
            en = v.get("text")
    return he, en


def _links_commentaries(ref, cats):
    """One links call → [(index_title, label_he, label_en)] for commentary-category links."""
    r = _get(f"{BASE}/api/links/{ref}", params={"with_text": 0})
    if not r:
        return []
    data = r.json()
    if not isinstance(data, list):     # error / non-list payload (e.g. large books, bad ref)
        return []
    out = []
    for lk in data:
        if not isinstance(lk, dict) or lk.get("category") not in cats:
            continue
        it = lk.get("index_title")
        if not it:
            continue
        ct = lk.get("collectiveTitle") or {}
        out.append((it, ct.get("he") or it, ct.get("en") or it))
    return out


def section_refs(domain, title, he):
    """Top-level section refs for per-section discovery (chapters / dafim) from the base structure."""
    n = len(he) if isinstance(he, list) else 0
    if domain == "gemara":
        refs = []
        for ai in range(n):
            daf, amud = (ai // 2) + 2, ("a" if ai % 2 == 0 else "b")
            refs.append(f"{title} {daf}{amud}")
        return refs
    return [f"{title} {i + 1}" for i in range(n)]


def discover_commentaries(base_title, secs, include_quoting):
    """All commentaries on a book. Whole-book links first; if that yields nothing
    (happens for large books like the Chumash), union per-section links instead."""
    cats = {"Commentary"} | ({"Quoting Commentary"} if include_quoting else set())
    found = {}
    for it, lhe, len_ in _links_commentaries(base_title, cats):
        found.setdefault(it, (lhe, len_))
    if not found:                       # fallback: scan each section and union
        for sref in secs:
            for it, lhe, len_ in _links_commentaries(sref, cats):
                found.setdefault(it, (lhe, len_))
            time.sleep(0.1)
    return [{"index_title": it, "label_he": v[0], "label_en": v[1]} for it, v in found.items()]


# ── chunking ──────────────────────────────────────────────────────────────────


def flatten(he, en, path=()):
    """Walk parallel nested he/en arrays → yield (addr_path, he_str, en_str) for each leaf."""
    if isinstance(he, list):
        for i, sub in enumerate(he):
            en_sub = en[i] if isinstance(en, list) and i < len(en) else None
            yield from flatten(sub, en_sub, path + (i,))
    else:
        he_s = he.strip() if isinstance(he, str) else ""
        en_s = en.strip() if isinstance(en, str) else ""
        if he_s or en_s:
            yield path, he_s, en_s


_slug = lambda s: re.sub(r"[^A-Za-z0-9]+", "", s)


def make_chunks(title, base_book, label_he, ctype, work_tag, he, en):
    """One Sefaria leaf segment = one chunk, in the project schema."""
    out = []
    for path, he_s, en_s in flatten(he, en):
        addr = ".".join(str(i + 1) for i in path)
        ref = f"{title} {addr}"
        doc = f"[{label_he}] {ref}\n{he_s}\n{en_s}".strip()
        cid = f"{_slug(title)}.{addr}_{_slug(label_he) or ctype}"
        out.append({
            "id": cid,
            "document": doc,
            "metadata": {
                "verse_id": ref,
                "ref": ref,
                "book": base_book,
                "chunk_type": ctype,
                "commentator": "" if ctype != "commentary" else label_he,
                "work": work_tag,
                "text_he": he_s,
                "text_en": en_s,
            },
        })
    return out


# ── build one domain ──────────────────────────────────────────────────────────


def build_domain(domain, include_quoting, do_upload, hf_token):
    base_fn, out_name, is_jsonl, work_tag = DOMAINS[domain]
    bases = DOMAIN_BASES[domain]
    PROC.mkdir(parents=True, exist_ok=True)
    work = PROC / f"full_{domain}.jsonl"          # streaming chunks
    done_path = PROC / f"full_{domain}.done"      # base texts finished

    done = set()
    if done_path.exists():
        done = {l.strip() for l in done_path.read_text(encoding="utf-8").splitlines() if l.strip()}
        print(f"[resume] {domain}: {len(done)}/{len(bases)} base texts already done")

    fout = work.open("a", encoding="utf-8")
    try:
        for bi, base in enumerate(bases, 1):
            if base in done:
                continue
            title = base_fn(base)
            print(f"\n[{domain} {bi}/{len(bases)}] 📖 {title}", flush=True)
            n_base = n_comm = n_works = 0

            # base text (with title fallback for odd mishnah names: Pirkei Avot / Uktzin)
            res = fetch_text(title)
            if (not res or not (res[0] or res[1])) and title != base:
                alt = fetch_text(base)
                if alt and (alt[0] or alt[1]):
                    title, res = base, alt
            he = res[0] if res else None
            if res and (res[0] or res[1]):
                ctype = "pasuk" if domain == "tanakh" else ("mishnah" if domain == "mishnah" else "gemara")
                chunks = make_chunks(title, base, base, ctype, work_tag, res[0], res[1])
                for c in chunks:
                    c["metadata"]["commentator"] = ""      # base text isn't a commentator
                    fout.write(json.dumps(c, ensure_ascii=False) + "\n")
                n_base = len(chunks)
            time.sleep(0.15)

            # all commentaries (dynamic; per-section fallback for large books)
            comms = discover_commentaries(title, section_refs(domain, title, he), include_quoting)
            print(f"    🔎 {len(comms)} commentaries linked", flush=True)
            for cm in comms:
                cres = fetch_text(cm["index_title"])
                if not cres or not (cres[0] or cres[1]):
                    time.sleep(0.1); continue
                chunks = make_chunks(cm["index_title"], base, cm["label_he"],
                                     "commentary", work_tag, cres[0], cres[1])
                if chunks:
                    for c in chunks:
                        fout.write(json.dumps(c, ensure_ascii=False) + "\n")
                    n_works += 1
                    n_comm += len(chunks)
                time.sleep(0.15)

            fout.flush()
            with done_path.open("a", encoding="utf-8") as df:
                df.write(base + "\n")
            print(f"    ✓ base {n_base:,} + commentary {n_comm:,} (from {n_works} works)", flush=True)
    finally:
        fout.close()

    # ── assemble to the canonical output file ──
    total = sum(1 for _ in work.open(encoding="utf-8"))
    out_path = PROC / out_name
    print(f"\n[assemble] {domain}: {total:,} chunks → {out_path}", flush=True)
    if is_jsonl:
        out_path.write_text(work.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        with out_path.open("w", encoding="utf-8") as o:
            o.write('{"metadata": ' + json.dumps({"total_chunks": total, "domain": domain},
                                                  ensure_ascii=False) + ', "chunks": [\n')
            with work.open(encoding="utf-8") as fin:
                for j, line in enumerate(fin):
                    o.write(line.rstrip("\n") + ("," if j + 1 < total else "") + "\n")
            o.write("]}\n")
    mb = out_path.stat().st_size / 1e6
    print(f"💾 {out_path} ({mb:.1f} MB, {total:,} chunks)", flush=True)

    if do_upload:
        from huggingface_hub import HfApi, create_repo
        create_repo(HF_REPO, repo_type="dataset", exist_ok=True, token=hf_token)
        print(f"⬆️  uploading {out_name} → {HF_REPO} (replacing existing)", flush=True)
        HfApi().upload_file(path_or_fileobj=str(out_path), path_in_repo=out_name,
                            repo_id=HF_REPO, repo_type="dataset", token=hf_token)
        print(f"✅ {domain} published → https://huggingface.co/datasets/{HF_REPO}/blob/main/{out_name}", flush=True)
    return total


def main():
    import os
    ap = argparse.ArgumentParser()
    ap.add_argument("--domain", choices=["tanakh", "gemara", "mishnah", "all"], required=True)
    ap.add_argument("--include-quoting", action="store_true",
                    help="גם 'Quoting Commentary' (עין יעקב וכו'), לא רק 'Commentary'")
    ap.add_argument("--no-upload", action="store_true", help="בנה בלבד, אל תעלה ל-HF")
    ap.add_argument("--token", default=os.environ.get("HF_TOKEN"))
    args = ap.parse_args()

    domains = ["tanakh", "gemara", "mishnah"] if args.domain == "all" else [args.domain]
    t0 = time.time()
    for d in domains:
        n = build_domain(d, args.include_quoting, not args.no_upload, args.token)
        print(f"\n=== {d}: {n:,} chunks in {(time.time()-t0)/60:.1f}m total ===", flush=True)
    print(f"\n✅ done ({(time.time()-t0)/60:.1f}m)")


if __name__ == "__main__":
    main()
