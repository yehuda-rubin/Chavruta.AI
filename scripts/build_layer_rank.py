#!/usr/bin/env python3
"""Rank every library category for content-search ordering: the order a learner meets the sources.

    Tanakh (Torah, Prophets, Writings) → Chazal (Mishnah, Tosefta, Gemara, Yerushalmi, Midrash)
    → Geonim → Rishonim → Acharonim → contemporary, and inside each era by genre
    (Tanakh commentary, Mishnah, Talmud, Midrash, halakhah, responsa, thought, musar, kabbalah, chasidut, liturgy).

A commentator is placed by HIS era, not by the book he comments on: Rashi on the Torah sits with the
Rishonim, the Malbim with the Acharonim, and both come after the Mishnah and Gemara. The era comes from
Sefaria's own index (`era`: GN/RI/AH/CO), fetched once per work family and cached in
src/chavruta/corpus/data/title_eras.json; the category path wins when it names an era
("Rishonim on Talmud").

Output: src/chavruta/corpus/data/layer_rank.json  {"<category path as stored in chunks>": rank}.
Lower rank first; ties fall back to the load order (rowid), which is canonical inside a book.

Usage:  .venv/Scripts/python.exe scripts/build_layer_rank.py [--no-fetch]
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "chavruta" / "corpus" / "data"

ERA_BASE = {"T": 100, "A": 150, "GN": 200, "RI": 300, "AH": 400, "CO": 500}   # Tannaim, Amoraim, Geonim, ...
ERA_OF_WORD = {"Geonim": "GN", "Rishonim": "RI", "Acharonim": "AH", "Modern": "CO"}
GENRE = {  # offset inside an era
    "Tanakh": 0, "Mishnah": 10, "Tosefta": 12, "Talmud": 20, "Midrash": 30, "Halakhah": 40, "Responsa": 50,
    "Jewish Thought": 60, "Musar": 70, "Kabbalah": 80, "Chasidut": 90, "Liturgy": 95,
}
DEFAULT_ERA = {"Chasidut": "AH", "Musar": "AH", "Responsa": "AH", "Halakhah": "AH", "Kabbalah": "RI",
               "Liturgy": "RI", "Jewish Thought": "AH", "Tanakh": "AH", "Mishnah": "AH", "Talmud": "AH",
               "Midrash": "AH", "Tosefta": "AH"}


# Works Sefaria records no era for. By family (the commentator, or the work itself); judged from the author's
# period: AH 16th–19th c., CO 20th c. onward, RI up to ~1500, GN geonic, A amoraic.
ERA_OVERRIDES = {
    # Yerushalmi and Bavli commentary
    "Mareh HaPanim": "AH", "Penei Moshe": "AH", "Sha'arei Torat Eretz Yisrael": "CO", "Amudei Yerushalayim": "CO",
    "Chiddushei Ridbaz": "AH", "Tosafot HaRid": "RI", "Haggahot Rabbi Menachem di Lonzano": "AH",
    "Korban HaEdah": "AH", "Sheyarei Korban": "AH", "Kikar LaAden": "AH",
    "Chidushei Rabbi Eliyahu of Greiditz": "AH", "Haggahot YaFeM": "AH", "Haggahot RaDO": "AH",
    "Gra's Nuschah": "AH", "Nachalat Ya'akov": "AH",
    # Mishnah, Tanakh, Midrash
    "Mishnat Eretz Yisrael": "CO", "Targum Jonathan": "A", "Yefeh Anaf": "AH",
    # Halakhah
    "Yad David": "AH", "Lechem Mishneh": "AH", "Chatam Sofer": "AH", "Peri Megadim": "AH",
    "Hilkhot Talmud Torah": "AH", "Kuntres Zikah": "AH", "Netiv Chesed": "AH", "Perush Kadmon": "RI",
    "Prisha": "AH", "Tiferet Yisrael": "AH", "Zohar HaRakia": "AH",
    # Chasidut, Jewish thought
    "Bnei Machshava Tova": "CO", "Ohr HaMeir": "AH", "Sha'arei Avodah": "AH", "Sha'arei HaYichud VeEmunah": "AH",
    "Yosher Divrei Emet": "AH", "Al Kapot HaMan'ul; Homilies for the Days of Awe": "CO", "Nishmat Chayyim": "AH",
    "Talmud Series; Shemitah": "CO", "Zikaron leYom Rishon": "CO",
    # Kabbalah
    "Mikdash Melekh, RaMaZ Commentary": "AH", "Pri Yitzhak": "AH", "Sefer HaBahir": "RI", "Sefer HaKanah": "RI",
    "Sefer Yetzirah": "GN", "Sefer Yetzirah Gra Version": "AH", "Sha'ar HaHakdamot": "AH", "Sha'ar HaKavanot": "AH",
    "Sha'ar HaMitzvot": "AH", "Sha'ar HaPesukim": "AH", "Sha'ar Ma'amarei Rashbi": "AH", "Sha'ar Ma'amarei Razal": "AH",
    "Sha'ar Ruach HaKodesh": "AH", "Yahel Ohr": "AH",
    # Liturgy: the prayer texts themselves are ancient; later piyyut and commentary by their authors
    "Azharot of Solomon ibn Gabirol": "RI", "Birkat Hamazon": "A", "Pesach Haggadah": "A", "Siddur Edot HaMizrach": "GN",
    "Weekday Siddur Sefard Linear": "GN", "Machzor Rosh Hashanah Ashkenaz": "GN", "Machzor Rosh Hashanah Ashkenaz Linear": "GN",
    "Machzor Yom Kippur Ashkenaz Linear": "GN", "Selichot Edot HaMizrach": "RI", "Selichot Nusach Ashkenaz Lita": "RI",
    "Selichot Nusach Lita Linear": "RI", "Selichot Nusach Polin": "RI", "Kinnot for Tisha B'Av (Ashkenaz)": "RI",
    "Leshon Chakhamim": "AH", "Ma'avar Yabbok": "AH", "Midrash BeChiddush": "AH", "Shalom Aleichem": "AH",
    "Zevach Pesach": "AH",
}


def family(title_en: str) -> str:
    if " on " in title_en:
        return title_en.split(" on ", 1)[0].strip()
    if title_en.startswith("Mishnah "):
        return "Mishnah"
    if "," in title_en:
        return title_en.split(",", 1)[0].strip()
    return title_en


def primary_rank(parts: list[str]) -> int | None:
    """Chazal and the written Torah: ranked by the text itself, ahead of every commentator."""
    top = parts[0]
    two = " / ".join(parts[:2])
    if two == "Tanakh / Torah":
        return 10
    if two == "Tanakh / Prophets":
        return 11
    if two == "Tanakh / Writings":
        return 12
    if top == "Mishnah" and len(parts) == 2 and parts[1].startswith("Seder "):
        return 20
    if top == "Tosefta" and len(parts) == 3 and parts[2].startswith("Seder "):
        return 21
    if top == "Talmud" and len(parts) == 3 and parts[1] == "Bavli" and parts[2].startswith("Seder "):
        return 30
    if top == "Talmud" and len(parts) == 3 and parts[1] == "Bavli" and parts[2] == "Minor Tractates":
        return 31
    if top == "Talmud" and len(parts) == 3 and parts[1] == "Yerushalmi" and parts[2].startswith("Seder "):
        return 32
    if top == "Midrash" and "Commentary" not in parts:
        return 40 if parts[1:2] == ["Halakhah"] else 41
    if top == "Second Temple":
        return 45
    return None


def fetch_eras(titles: dict[str, str], cache: dict[str, str | None], pause: float) -> None:
    todo = [f for f in titles if f not in cache]
    print(f"eras to fetch: {len(todo)} (cached {len(cache)})")
    for i, fam in enumerate(todo, 1):
        era = None
        try:
            r = requests.get("https://www.sefaria.org/api/v2/index/" + requests.utils.quote(titles[fam]), timeout=30)
            if r.ok:
                era = (r.json() or {}).get("era")
        except requests.RequestException:
            era = None
        cache[fam] = era
        if i % 50 == 0:
            (DATA / "title_eras.json").write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
            print(f"  {i}/{len(todo)}")
        time.sleep(pause)
    (DATA / "title_eras.json").write_text(json.dumps(cache, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--pause", type=float, default=0.15)
    args = ap.parse_args()

    books = json.loads((DATA / "catalog.json").read_text(encoding="utf-8"))["books"]
    rep: dict[str, str] = {}
    for b in books:
        rep.setdefault(family(b["title_en"]), b["title_en"])
    cache_path = DATA / "title_eras.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    if not args.no_fetch:
        fetch_eras(rep, cache, args.pause)

    ranks: dict[str, int] = {}
    defaulted: dict[tuple[str, str], int] = {}
    stats = {"primary": 0, "era-from-path": 0, "era-from-sefaria": 0, "era-default": 0}
    for b in books:
        parts = b["path"].split("/")
        path_key = " / ".join(parts)                       # how chunks.category_path stores it
        rank = primary_rank(parts)
        if rank is not None:
            stats["primary"] += 1
            ranks[path_key] = min(ranks.get(path_key, rank), rank)
            continue
        top = parts[0]
        era = next((ERA_OF_WORD[p.split(" on ")[0]] for p in parts if p.split(" on ")[0] in ERA_OF_WORD), None)
        if era:
            stats["era-from-path"] += 1
        else:
            fam = family(b["title_en"])
            era = ERA_OVERRIDES.get(fam) or cache.get(fam)
            if era in ERA_BASE:
                stats["era-from-sefaria"] += 1
            else:
                era = DEFAULT_ERA.get(top, "AH")
                stats["era-default"] += 1
                defaulted.setdefault((top, fam), 0)
                defaulted[(top, fam)] += 1
        rank = ERA_BASE[era] + GENRE.get(top, 99)
        if top == "Reference":
            rank = 900
        # one path can hold books of different eras (e.g. Mishneh Torah commentary): keep the earliest
        ranks[path_key] = min(ranks.get(path_key, rank), rank)

    out = DATA / "layer_rank.json"
    out.write_text(json.dumps(ranks, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    print(f"{len(ranks)} category paths ranked; per book: {stats}")
    for (t, f), n in sorted(defaulted.items(), key=lambda x: -x[1])[:40]:
        print("  still defaulted:", n, t, "|", f)
    print("wrote", out)


if __name__ == "__main__":
    main()
