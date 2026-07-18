#!/usr/bin/env python3
"""fetch_licensed_local.py — build the commercial corpus LOCALLY, one tier at a time, and after each
tier: upload its chunks + licence docs to its own HF dataset, then DELETE the local files.

Same logic as notebooks/fetch_licensed_kaggle.ipynb (verified there), run as a resumable local job:
for every source in a Sefaria tier — base text or commentary — pick the single best commercially
licensed edition (least-encumbered, prefer vocalized), fetch only that, record the licence per
chunk, skip sources with no commercial edition, and per tier write <slug>.jsonl + licenses.json +
README.md → upload to Yehuda-Rubin/chavruta-commercial-<slug> → remove the local files.

CPU / network-bound. Resumable: a tier already present on HF is skipped; within a tier a .done set
skips finished works. Ordered smallest→largest so quick tiers land first.

    python scripts/fetch_licensed_local.py                 # all remaining tiers
    python scripts/fetch_licensed_local.py --only musar     # one tier
    python scripts/fetch_licensed_local.py --keep-local     # don't delete after upload
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, OrderedDict
from datetime import datetime, UTC
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chavruta.corpus.rights import allows_commercial_use  # noqa: E402

HF_NAMESPACE = "Yehuda-Rubin"
REPO_PREFIX = "chavruta-commercial-"
WORK = ROOT / "data" / "commercial_fetch"
BASE = "https://www.sefaria.org"
PREFER_NIKKUD = True
SLEEP = 0.15

# slug → (Sefaria category, keep-predicate). Smallest→largest. tanakh/mishnah/talmud already have the
# 4 base domains, but here every tier is fetched uniformly (base + all commentaries) commercial-only.
TIERS = OrderedDict([
    ("second_temple",  ("Second Temple",  None)),
    ("reference",      ("Reference",      None)),
    ("musar",          ("Musar",          None)),
    ("tosefta",        ("Tosefta",        None)),
    ("liturgy",        ("Liturgy",        None)),
    ("kabbalah",       ("Kabbalah",       None)),
    ("midrash",        ("Midrash",        None)),
    ("chasidut",       ("Chasidut",       None)),
    ("jewish_thought", ("Jewish Thought", None)),
    ("shut",           ("Responsa",       None)),
    ("yerushalmi",     ("Talmud",         lambda w: "Jerusalem Talmud" in w["title"])),
    ("mishnah",        ("Mishnah",        None)),
    ("tanakh",         ("Tanakh",         None)),
    ("halacha",        ("Halakhah",       None)),
    ("gemara",         ("Talmud",         lambda w: "Jerusalem Talmud" not in w["title"])),
])

S = requests.Session()
S.headers.update({"User-Agent": "Chavruta.AI/0.2 (educational Torah RAG; commercial-licence fetch)"})


# ── token ────────────────────────────────────────────────────────────────────
def load_hf_token() -> str:
    """Env → .env → .claude/settings.json. Never printed; kept out of the command line."""
    tok = os.environ.get("HF_TOKEN")
    if tok:
        return tok.strip()
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*HF_TOKEN\s*=\s*['\"]?([^'\"]+)", line)
            if m:
                return m.group(1).strip()
    settings = ROOT / ".claude" / "settings.json"
    if settings.exists():
        m = re.search(r"HF_TOKEN='([^']+)'", settings.read_text(encoding="utf-8"))
        if m:
            return m.group(1)
    raise SystemExit("no HF token found (env HF_TOKEN / .env / .claude/settings.json)")


# ── Sefaria ──────────────────────────────────────────────────────────────────
def _get_json(path, params=None, retries=4):
    url = f"{BASE}/api/{path}"
    for a in range(retries):
        try:
            r = S.get(url, params=params, timeout=120)
        except requests.RequestException:
            time.sleep(2 * (a + 1)); continue
        if r.status_code == 404:
            return None
        if r.status_code == 200:
            try:
                return r.json()
            except Exception:
                return None
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(3 * (a + 1)); continue
        return None
    return None


_VCACHE: dict = {}
def versions(title):
    if title not in _VCACHE:
        d = _get_json(f"texts/versions/{urllib.parse.quote(title)}")
        _VCACHE[title] = d if isinstance(d, list) else []
        time.sleep(0.05)
    return _VCACHE[title]


def fetch_text(ref, he_version=None, en_version=None, want_he=True, want_en=True):
    vparams = []
    if want_he:
        vparams.append(f"hebrew|{he_version}" if he_version else "hebrew")
    if want_en:
        vparams.append(f"english|{en_version}" if en_version else "english")
    if not vparams:
        return None
    data = _get_json(f"v3/texts/{urllib.parse.quote(ref)}",
                     params={"version": vparams, "return_format": "text_only"})
    if not data:
        return None
    he = en = None
    rights = {"he": {"license": "", "version_title": ""}, "en": {"license": "", "version_title": ""}}
    for v in data.get("versions", []):
        fam = (v.get("languageFamilyName") or v.get("language") or "").lower()
        meta = {"license": v.get("license") or "", "version_title": v.get("versionTitle") or ""}
        if fam.startswith("he") and he is None:
            he, rights["he"] = v.get("text"), meta
        elif fam.startswith("en") and en is None:
            en, rights["en"] = v.get("text"), meta
    return he, en, rights


PERIOD_OVERRIDE = {"Geonim": "geonim", "Rishonim": "rishonim", "Acharonim": "acharonim", "Modern": "modern"}
def slugify(c): return re.sub(r"[^a-z0-9]+", "_", c.lower()).strip("_")


_WCACHE: dict = {}
def load_works(category):
    if category not in _WCACHE:
        toc = _get_json("index/")
        root = next((c for c in toc if c.get("category") == category), None)
        if root is None:
            raise SystemExit(f"category {category!r} not found")
        works = []

        def walk(node, period, path):
            cat = node.get("category", "")
            period = PERIOD_OVERRIDE.get(cat, period)
            path = path + [cat] if cat else path
            for ch in node.get("contents", []):
                if "contents" in ch:
                    walk(ch, period, path)
                elif ch.get("title"):
                    works.append({"title": ch["title"], "he_title": ch.get("heTitle", ""),
                                  "period": period, "category_path": " / ".join(path)})

        walk(root, slugify(category), [])
        _WCACHE[category] = works
    return _WCACHE[category]


def _node_titles(node):
    en = he = ""
    for t in node.get("titles", []):
        if t.get("primary"):
            if t.get("lang") == "en":
                en = t.get("text", "")
            elif t.get("lang") == "he":
                he = t.get("text", "")
    return en or node.get("key", ""), he


def leaf_ref_bases(title, he_title):
    idx = _get_json(f"v2/raw/index/{urllib.parse.quote(title)}")
    schema = (idx or {}).get("schema", {})
    out = []

    def walk(node, en_ref, he_ref, section_en):
        if "nodes" in node:
            for ch in node["nodes"]:
                en_t, he_t = _node_titles(ch)
                if ch.get("default") or not en_t:
                    walk(ch, en_ref, he_ref, section_en)
                else:
                    walk(ch, f"{en_ref}, {en_t}", f"{he_ref}, {he_t}" if he_t else he_ref,
                         en_t if not section_en else f"{section_en} / {en_t}")
        else:
            out.append((en_ref, he_ref, section_en))

    if "nodes" in schema:
        walk(schema, title, he_title, "")
    else:
        out.append((title, he_title, ""))
    return out


# ── commercial version selection ──────────────────────────────────────────────
def _lic_rank(lic):
    x = (lic or "").strip().lower()
    if x in {"public domain", "public domain mark", "pd", "cc0", "cc0 1.0", "cc zero"}:
        return 2
    if x.startswith(("cc-by", "cc by")) and "sa" not in x:
        return 1
    return 0


def _has_nikkud(vt):
    return any(k in (vt or "") for k in ("Nikkud", "nikkud", "Vocaliz", "vocaliz", "Ta'amei", "Masorah"))


def pick_commercial(title, lang):
    cands = [v for v in versions(title)
             if (v.get("language") or "").lower().startswith(lang) and allows_commercial_use(v.get("license"))]
    if not cands:
        return None
    best = max(cands, key=lambda v: (_lic_rank(v.get("license")),
                                     _has_nikkud(v.get("versionTitle")) if PREFER_NIKKUD else 0,
                                     1 if v.get("isPrimary") else 0, v.get("priority") or 0))
    return {"version_title": best.get("versionTitle") or "", "license": best.get("license") or ""}


# ── chunks ────────────────────────────────────────────────────────────────────
def _seg(x):
    if isinstance(x, list):
        return " ".join(_seg(i) for i in x if i).strip()
    return (x or "").strip() if isinstance(x, str) else ""


def _walk_leaves(he, en, path):
    if isinstance(he, list):
        for i, sub in enumerate(he):
            en_sub = en[i] if isinstance(en, list) and i < len(en) else None
            yield from _walk_leaves(sub, en_sub, path + [i + 1])
    else:
        yield path, (he if isinstance(he, str) else ""), (en if isinstance(en, str) else "")


def build_chunks(work, slug, en_ref, section_en, he_nested, en_nested, rights, kept, dropped):
    he_r, en_r = rights.get("he") or {}, rights.get("en") or {}
    he_lic, en_lic = he_r.get("license", ""), en_r.get("license", "")
    he_ok, en_ok = allows_commercial_use(he_lic), allows_commercial_use(en_lic)
    book, he_book = work["title"], (work["he_title"] or work["title"])
    out = []
    for path, he_t, en_t in _walk_leaves(he_nested, en_nested, []):
        he_t, en_t = _seg(he_t), _seg(en_t)
        keep_he = he_t if (he_ok and he_t) else ""
        keep_en = en_t if (en_ok and en_t) else ""
        if he_t and not he_ok:
            dropped[he_lic or "(unknown)"] += 1
        if en_t and not en_ok:
            dropped[en_lic or "(unknown)"] += 1
        if not (keep_he or keep_en):
            continue
        if keep_he:
            kept[he_lic] += 1
        if keep_en:
            kept[en_lic] += 1
        path_str = ".".join(str(p) for p in path) or "1"
        verse_id = f"{en_ref}.{path_str}".replace(" ", "_")
        ref_label = f"{en_ref} {':'.join(str(p) for p in path)}".strip()
        doc = f"[{he_book}] {ref_label}\n{keep_he}\n{keep_en}".strip()
        out.append({"id": f"{verse_id}_{slug}", "document": doc, "metadata": {
            "verse_id": verse_id, "ref": ref_label, "book": book,
            "chapter": path[0] if path else 1, "verse": path[-1] if path else 1,
            "chunk_type": slug, "commentator": "", "work": slug, "period": work["period"],
            "author_he": he_book, "section": section_en, "category_path": work["category_path"],
            "text_he": keep_he, "text_en": keep_en,
            "license_he": he_lic, "version_he": he_r.get("version_title", ""),
            "license_en": en_lic, "version_en": en_r.get("version_title", ""),
        }})
    return out


# ── one tier ──────────────────────────────────────────────────────────────────
def build_tier(slug):
    category, keep = TIERS[slug]
    works = load_works(category)
    if keep:
        works = [w for w in works if keep(w)]
    WORK.mkdir(parents=True, exist_ok=True)
    out_jsonl = WORK / f"{slug}.jsonl"
    done_path = WORK / f"{slug}.done"
    man_path = WORK / f"{slug}.manifest.jsonl"
    done = set()
    if done_path.exists():
        done = {l.strip() for l in done_path.read_text(encoding="utf-8").splitlines() if l.strip()}
    print(f"[{slug}] {category}: {len(works)} works, {len(done)} done", flush=True)
    kept, dropped, skipped = Counter(), Counter(), []
    fout = out_jsonl.open("a", encoding="utf-8")
    mout = man_path.open("a", encoding="utf-8")
    try:
        for i, work in enumerate(works, 1):
            title = work["title"]
            if title in done:
                continue
            he_sel, en_sel = pick_commercial(title, "he"), pick_commercial(title, "en")
            rec = {"title": title, "he_title": work["he_title"], "period": work["period"],
                   "he_license": (he_sel or {}).get("license", ""), "he_version": (he_sel or {}).get("version_title", ""),
                   "en_license": (en_sel or {}).get("license", ""), "en_version": (en_sel or {}).get("version_title", ""),
                   "chunks": 0, "status": "kept"}
            if not he_sel and not en_sel:
                skipped.append(title)
                rec["status"] = "skipped_no_commercial_edition"
                mout.write(json.dumps(rec, ensure_ascii=False) + "\n"); mout.flush()
                done_path.open("a", encoding="utf-8").write(title + "\n")
                continue
            n = 0
            for en_ref, he_ref, section_en in leaf_ref_bases(title, work["he_title"]):
                res = fetch_text(en_ref,
                                 he_version=he_sel["version_title"] if he_sel else None,
                                 en_version=en_sel["version_title"] if en_sel else None,
                                 want_he=bool(he_sel), want_en=bool(en_sel))
                if not res or not (res[0] or res[1]):
                    time.sleep(0.15); continue
                for c in build_chunks(work, slug, en_ref, section_en, *res, kept, dropped):
                    fout.write(json.dumps(c, ensure_ascii=False) + "\n"); n += 1
                time.sleep(SLEEP)
            fout.flush()
            rec["chunks"] = n
            mout.write(json.dumps(rec, ensure_ascii=False) + "\n"); mout.flush()
            done_path.open("a", encoding="utf-8").write(title + "\n")
            if i % 10 == 0 or n:
                print(f"  [{i}/{len(works)}] {title[:40]:40} {(he_sel or en_sel)['license']:12} +{n}", flush=True)
    finally:
        fout.close(); mout.close()
    manifest = [json.loads(l) for l in man_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    n_rows = sum(1 for _ in out_jsonl.open(encoding="utf-8")) if out_jsonl.exists() else 0
    print(f"  ✅ {slug}: {n_rows:,} chunks, {len(manifest)} sources, {len(skipped)} skipped", flush=True)
    return out_jsonl, n_rows, manifest


def write_docs(slug, manifest):
    kept = [m for m in manifest if m["status"] == "kept"]
    skipped = [m for m in manifest if m["status"] != "kept"]
    lic_mix, editions = Counter(), OrderedDict()
    for m in kept:
        for lv, vv in ((m["he_license"], m["he_version"]), (m["en_license"], m["en_version"])):
            if not lv:
                continue
            lic_mix[lv] += 1
            editions.setdefault((vv, lv), 0)
            editions[(vv, lv)] += 1
    lic_json = WORK / f"{slug}.licenses.json"
    json.dump({"tier": slug, "generated_utc": datetime.now(UTC).isoformat(),
               "kept_sources": len(kept), "skipped_sources": len(skipped),
               "license_mix": dict(lic_mix), "sources": manifest},
              lic_json.open("w", encoding="utf-8"), ensure_ascii=False, indent=1)
    lines = [f"# Chavruta.AI — commercial corpus: **{slug}**", "",
             "Licensed text from [Sefaria](https://www.sefaria.org), fetched for **commercial** use.",
             "Only editions permitting commercial reproduction (Public Domain / CC0 / CC-BY / CC-BY-SA)",
             "were kept — one per source. Sources with no commercial edition were excluded. Each chunk",
             "carries its `license_he`/`license_en` and `version_he`/`version_en`.", "",
             "> Not legal advice. NonCommercial (CC-BY-NC) and copyright-restricted text is excluded.", "",
             "## Licence mix", ""]
    for lv, n in lic_mix.most_common():
        lines.append(f"- **{lv}** — {n:,}")
    lines += ["", f"Kept sources: {len(kept):,} · Excluded: {len(skipped):,}", "",
              "## Attribution — editions used", "",
              "| Edition (versionTitle) | Licence | # sources |", "|---|---|---|"]
    for (vv, lv), cnt in sorted(editions.items(), key=lambda kv: -kv[1]):
        lines.append(f"| {vv or '(default)'} | {lv} | {cnt} |")
    readme = WORK / f"{slug}.README.md"
    readme.write_text("\n".join(lines), encoding="utf-8")
    return lic_json, readme


def upload_and_clean(slug, out_jsonl, lic_json, readme, token, keep_local):
    from huggingface_hub import HfApi, create_repo
    repo = f"{HF_NAMESPACE}/{REPO_PREFIX}{slug}"
    create_repo(repo, repo_type="dataset", exist_ok=True, token=token)
    api = HfApi()
    for path, name in ((out_jsonl, f"{slug}.jsonl"), (lic_json, "licenses.json"), (readme, "README.md")):
        print(f"  ⬆️  {name} → {repo}", flush=True)
        api.upload_file(path_or_fileobj=str(path), path_in_repo=name, repo_id=repo,
                        repo_type="dataset", token=token)
    if not keep_local:
        for p in (out_jsonl, lic_json, readme, WORK / f"{slug}.done", WORK / f"{slug}.manifest.jsonl"):
            try:
                p.unlink()
            except FileNotFoundError:
                pass
        print(f"  🗑️  removed local files for {slug}", flush=True)


def already_on_hf(slug, token) -> bool:
    from huggingface_hub import HfApi
    try:
        files = HfApi().list_repo_files(f"{HF_NAMESPACE}/{REPO_PREFIX}{slug}", repo_type="dataset", token=token)
        return f"{slug}.jsonl" in files and "licenses.json" in files
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="run a single tier slug")
    ap.add_argument("--keep-local", action="store_true", help="do not delete local files after upload")
    ap.add_argument("--force", action="store_true", help="rebuild even if already on HF")
    args = ap.parse_args()
    token = load_hf_token()
    slugs = [args.only] if args.only else list(TIERS)
    for slug in slugs:
        if slug not in TIERS:
            print(f"skip unknown tier {slug!r}"); continue
        if not args.force and already_on_hf(slug, token):
            print(f"[{slug}] already on HF — skipping (use --force to rebuild)", flush=True)
            continue
        t0 = time.time()
        out_jsonl, n, manifest = build_tier(slug)
        if n == 0:
            print(f"[{slug}] produced 0 chunks — not uploading", flush=True)
            continue
        lic_json, readme = write_docs(slug, manifest)
        upload_and_clean(slug, out_jsonl, lic_json, readme, token, args.keep_local)
        print(f"[{slug}] DONE in {(time.time()-t0)/60:.1f} min\n", flush=True)


if __name__ == "__main__":
    main()
