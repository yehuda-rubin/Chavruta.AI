# -*- coding: utf-8 -*-
"""Build the Talmud perek→opening-ref index from Sefaria, in the CORPUS ref format.

Sefaria's index alt_structs give each perek's daf range ('Sanhedrin 23a:1-31b:21' → opens 23a).
The Chavruta corpus stores Talmud base texts with a FLAT amud-linear number, not the amud letter:
corpus N = 2·daf − 1 for amud 'a', 2·daf for amud 'b' (verified: 2a→3, 23a→45, 12a→23). So the
opening of perek P of tractate T is stored as 'T <N>.1'. This script fetches every Bavli tractate,
converts each perek's opening daf → corpus N, and writes the map to
src/chavruta/intents/data/talmud_perek_daf.json so the router can resolve 'פרק <n> ב<מסכת>' offline.

    python scripts/build_talmud_perek_index.py
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from chavruta.corpus.refs import daf_amud_to_corpus_n  # single source of truth for N = 2·daf ∓ 1

# Standard 37 Bavli tractates (Sefaria English titles → Hebrew names for the router).
TRACTATES = {
    "Berakhot": "ברכות", "Shabbat": "שבת", "Eruvin": "עירובין", "Pesachim": "פסחים",
    "Rosh Hashanah": "ראש השנה", "Yoma": "יומא", "Sukkah": "סוכה", "Beitzah": "ביצה",
    "Taanit": "תענית", "Megillah": "מגילה", "Moed Katan": "מועד קטן", "Chagigah": "חגיגה",
    "Yevamot": "יבמות", "Ketubot": "כתובות", "Nedarim": "נדרים", "Nazir": "נזיר",
    "Sotah": "סוטה", "Gittin": "גיטין", "Kiddushin": "קידושין", "Bava Kamma": "בבא קמא",
    "Bava Metzia": "בבא מציעא", "Bava Batra": "בבא בתרא", "Sanhedrin": "סנהדרין",
    "Makkot": "מכות", "Shevuot": "שבועות", "Avodah Zarah": "עבודה זרה", "Horayot": "הוריות",
    "Zevachim": "זבחים", "Menachot": "מנחות", "Chullin": "חולין", "Bekhorot": "בכורות",
    "Arakhin": "ערכין", "Temurah": "תמורה", "Keritot": "כריתות", "Meilah": "מעילה",
    "Tamid": "תמיד", "Niddah": "נדה",
}

# Opening of a perek's wholeRef: 'Sanhedrin 23a:1-31b:21' / 'Berakhot 17b:12-26a:10' → daf, amud, seg.
_OPEN_RE = re.compile(r"\b(\d+)([ab]):(\d+)")


def _fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "chavruta-index/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    out: dict[str, dict] = {}
    for en, he in TRACTATES.items():
        try:
            idx = _fetch(f"https://www.sefaria.org/api/v2/raw/index/{en.replace(' ', '%20')}")
            nodes = ((idx.get("alt_structs") or {}).get("Chapters") or {}).get("nodes") or []
            perakim: list[str] = []
            for n in nodes:
                whole = n.get("wholeRef") or ""
                m = _OPEN_RE.search(whole)                # opening daf:amud:segment of the perek
                if not m:
                    perakim.append("")
                    continue
                daf, amud, seg = int(m.group(1)), m.group(2), int(m.group(3))
                # corpus segment index mirrors Sefaria's within-amud index 1:1 (verified live), so the
                # perek opens at 'Tractate N.seg' — NOT '.1' (69% of perakim open mid-amud).
                perakim.append(f"{en} {daf_amud_to_corpus_n(daf, amud)}.{seg}")
            if perakim:
                out[en] = {"he": he, "perakim": perakim}
                print(f"  {en}: {len(perakim)} perakim  (perek3={perakim[2] if len(perakim) > 2 else '-'})")
        except Exception as exc:
            print(f"  ! {en}: {str(exc)[:80]}")
        time.sleep(0.3)                                    # be polite to Sefaria

    dest = Path(__file__).resolve().parents[1] / "src" / "chavruta" / "intents" / "data" / "talmud_perek_daf.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nwrote {len(out)} tractates → {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
