# -*- coding: utf-8 -*-
"""
sefaria_client.py — קליינט קל ל-Sefaria API (חינמי, בלי מפתח).
─────────────────────────────────────────────────────────────────────────────
מביא פסוק + מפרשים בעברית ובאנגלית. משמש את:
  • שלב 1 — אחזור עשיר על פסוק ספציפי (on-demand).
  • שלב 3 — הרחבת הקורפוס (לבולק כדאי Sefaria-Export, לא ה-API החי).

מקור התיעוד: developers.sefaria.org (אומת חי 2026-06).
"""

from __future__ import annotations
import time
import requests

BASE = "https://www.sefaria.org"
_HEADERS = {"User-Agent": "Chavruta.AI/0.1 (educational Torah RAG)"}

# שמות המפרשים שלנו → collectiveTitle.en של Sefaria (ראה docs/CORPUS.md)
COMMENTATORS = [
    "Rashi", "Ramban", "Ibn Ezra", "Radak", "Sforno", "Rashbam",
    "Or HaChaim", "Malbim", "Baal HaTurim", "Metzudat David", "Metzudat Zion",
]
TARGUMIM = ["Onkelos", "Targum Jonathan"]   # category == "Targum"

_session = requests.Session()
_session.headers.update(_HEADERS)


def _get(url: str, params: dict | None = None, retries: int = 3) -> dict | list:
    """GET עם נימוס: retry/backoff על 429/5xx."""
    for attempt in range(retries):
        r = _session.get(url, params=params, timeout=30)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(1.5 * (attempt + 1))
            continue
        r.raise_for_status()
    r.raise_for_status()
    return {}


def _split_he_en(versions: list) -> tuple[str, str]:
    """מתוך מערך ה-versions של v3 — מחזיר (he, en) כמחרוזות."""
    he = en = ""
    for v in versions or []:
        fam = (v.get("languageFamilyName") or v.get("language") or "").lower()
        txt = v.get("text")
        if isinstance(txt, list):                 # range/section → איחוד
            txt = " ".join(t for t in txt if isinstance(t, str))
        txt = (txt or "").strip()
        if fam.startswith("he") and not he:
            he = txt
        elif fam.startswith("en") and not en:
            en = txt
    return he, en


def get_text(ref: str) -> dict:
    """
    מביא טקסט של הפניה אחת (פסוק/קטע) בעברית+אנגלית.
    ref למשל: 'Genesis 1:1' או 'Rashi on Genesis 1:1'.
    מחזיר: {ref, he, en}
    """
    data = _get(
        f"{BASE}/api/v3/texts/{ref}",
        params={"version": ["hebrew", "english"], "return_format": "text_only"},
    )
    he, en = _split_he_en(data.get("versions", []))
    return {"ref": ref, "he": he, "en": en}


def get_commentaries(ref: str, names: list[str] | None = None,
                     include_targum: bool = True) -> list[dict]:
    """
    מביא את כל המפרשים (מרשימת COMMENTATORS, או names מותאם) על פסוק.
    מחזיר רשימת {commentator, ref, he, en} — ממוין לפי סדר הופעה.
    """
    wanted = set(names or COMMENTATORS)
    if include_targum:
        wanted |= set(TARGUMIM)

    links = _get(f"{BASE}/api/links/{ref}", params={"with_text": 0})
    if not isinstance(links, list):
        return []

    # אסוף refs רלוונטיים לפי collectiveTitle.en, בשמירת סדר
    seen, picked = set(), []
    for ln in links:
        title = (ln.get("collectiveTitle") or {}).get("en", "")
        cat = ln.get("category", "")
        if title in wanted and (cat in ("Commentary", "Targum")):
            r = ln.get("ref")
            if r and r not in seen:
                seen.add(r)
                picked.append((title, r))

    out = []
    for title, r in picked:
        t = get_text(r)
        if t["he"] or t["en"]:
            out.append({"commentator": title, "ref": r, "he": t["he"], "en": t["en"]})
    return out


def get_verse_bundle(ref: str, names: list[str] | None = None) -> dict:
    """פסוק + כל מפרשיו — חבילה אחת מוכנה ל-RAG/הצגה."""
    verse = get_text(ref)
    return {
        "ref": ref,
        "pasuk": {"he": verse["he"], "en": verse["en"]},
        "commentaries": get_commentaries(ref, names=names),
    }


if __name__ == "__main__":
    import json
    bundle = get_verse_bundle("Genesis 1:1", names=["Rashi", "Ramban", "Ibn Ezra"])
    print(json.dumps(bundle, ensure_ascii=False, indent=2)[:1500])
