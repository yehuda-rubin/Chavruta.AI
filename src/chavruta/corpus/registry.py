"""CorpusRegistry — adding a Work is a data/config operation (Constitution Principle III).

The registry describes every body of texts (Tanakh today; Gemara/Halacha/Emunah later) and
how to ingest it. Retrieval/ranking/generation never change when a Work is added — they read
the registry and scope by `work_id`.
"""

from __future__ import annotations

import json
from pathlib import Path

from chavruta.corpus.schema import Work


class CorpusRegistry:
    def __init__(self) -> None:
        self._works: dict[str, Work] = {}

    def register(self, work: Work) -> None:
        if work.work_id in self._works:
            # Idempotent re-register (e.g. re-running ingestion) updates metadata.
            pass
        self._works[work.work_id] = work

    def get(self, work_id: str) -> Work:
        return self._works[work_id]

    def has(self, work_id: str) -> bool:
        return work_id in self._works

    def list_ids(self) -> list[str]:
        return list(self._works.keys())

    def list_works(self) -> list[Work]:
        return list(self._works.values())

    # ── persistence (the registry is data) ──
    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = [vars(w) | {"languages": list(w.languages)} for w in self._works.values()]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "CorpusRegistry":
        reg = cls()
        p = Path(path)
        if not p.exists():
            return reg
        for d in json.loads(p.read_text(encoding="utf-8")):
            d["languages"] = tuple(d.get("languages", ("he", "en")))
            reg.register(Work(**d))
        return reg


# The default Tanakh work registered for the MVP.
TANAKH = Work(
    work_id="tanakh",
    title_he="תנ\"ך",
    title_en="Tanakh",
    kind="scripture",
    languages=("he", "en"),
    reference_scheme="book/chapter/verse",
    source_adapter="sefaria",
    license="CC0 / Sefaria",
    attribution="Sefaria (sefaria.org)",
)

MISHNAH = Work(
    work_id="mishnah",
    title_he="משנה",
    title_en="Mishnah",
    kind="mishnah",
    languages=("he", "en"),
    reference_scheme="tractate/chapter/mishnah",
    source_adapter="sefaria",
    license="CC0 / Sefaria",
    attribution="Sefaria (sefaria.org)",
)

TALMUD_BAVLI = Work(
    work_id="talmud_bavli",
    title_he="תלמוד בבלי",
    title_en="Talmud Bavli",
    kind="talmud",
    languages=("he", "en"),
    reference_scheme="tractate/daf/amud",
    source_adapter="sefaria",
    license="CC0 / Sefaria",
    attribution="Sefaria (sefaria.org)",
)

# Responsa (שו"ת) — the full Sefaria responsa library (גאונים · ראשונים · אחרונים · מודרני),
# ingested into the SAME collection. Each chunk carries work_id="responsa" and its halachic
# `period`; segments span many authors, so the reference scheme is the work's own segment path.
RESPONSA = Work(
    work_id="responsa",
    title_he="שו\"ת",
    title_en="Responsa",
    kind="responsa",
    languages=("he", "en"),
    reference_scheme="work/section/segment",
    source_adapter="sefaria",
    license="CC0 / Sefaria",
    attribution="Sefaria (sefaria.org)",
)


# The categories actually loaded into the corpus (payload `work_id` values in Qdrant). The honesty
# gate must know ALL of them — otherwise it falsely refuses to answer about loaded material (e.g. the
# whole Talmud) just because it wasn't registered. Keep in sync with scripts/load_all_indexes.py.
_LOADED_CATEGORIES: dict[str, tuple[str, str, str]] = {
    "tanakh": ("תנ\"ך", "Tanakh", "scripture"),
    "mishnah": ("משנה", "Mishnah", "mishnah"),
    "talmud_bavli": ("תלמוד בבלי", "Talmud Bavli", "talmud"),
    "tosefta": ("תוספתא", "Tosefta", "talmud"),
    "midrash": ("מדרש", "Midrash", "midrash"),
    "halacha": ("הלכה", "Halacha", "halacha"),
    "responsa": ("שו\"ת", "Responsa", "responsa"),
    "kabbalah": ("קבלה", "Kabbalah", "kabbalah"),
    "chasidut": ("חסידות", "Chasidut", "chasidut"),
    "musar": ("מוסר", "Musar", "musar"),
    "jewish_thought": ("מחשבה", "Jewish Thought", "machshava"),
    "liturgy": ("סידור ותפילה", "Liturgy", "liturgy"),
    "reference": ("עיון ועזר", "Reference", "reference"),
    "second_temple": ("ספרות בית שני", "Second Temple", "second_temple"),
}
# router WORK_ALIASES key → the loaded category it actually lives in, so the honesty gate recognizes
# 'הגמרא', 'שולחן ערוך', 'רמב"ם', 'זוהר' as present (they're inside these categories).
_ALIAS_CATEGORY: dict[str, str] = {
    "talmud": "talmud_bavli",
    "shulchan_aruch": "halacha", "mishneh_torah": "halacha", "mishnah_berurah": "halacha", "tur": "halacha",
    "zohar": "kabbalah",
}


def default_registry() -> CorpusRegistry:
    reg = CorpusRegistry()
    for wid, (he, en, kind) in _LOADED_CATEGORIES.items():
        reg.register(Work(work_id=wid, title_he=he, title_en=en, kind=kind, languages=("he", "en"),
                          reference_scheme="work/section/segment", source_adapter="sefaria",
                          license="CC0 / Sefaria", attribution="Sefaria (sefaria.org)"))
    for alias, cat in _ALIAS_CATEGORY.items():
        if reg.has(cat) and not reg.has(alias):
            c = reg.get(cat)
            reg.register(Work(work_id=alias, title_he=c.title_he, title_en=c.title_en, kind=c.kind,
                              languages=c.languages, reference_scheme=c.reference_scheme,
                              source_adapter=c.source_adapter, license=c.license, attribution=c.attribution))
    return reg
