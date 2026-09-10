"""test_lesson_templates_en.py — Unit tests for English lesson templates and backend job formatting."""

import pytest
from pathlib import Path
import yaml

from app.api import (
    _attach_template_bodies,
    _lesson_job_md,
    _source_sheet_entry,
    _BAND_PED_EN,
    _LENGTHS,
    CitationOut,
    _REPO_DIR,
)


class DummyHit:
    def __init__(self, ref: str, text: str = "", text_he: str = "", text_en: str = "", commentator_id: str = ""):
        self.ref = ref
        self.text = text or text_he or text_en
        self.text_he = text_he
        self.text_en = text_en
        self.commentator_id = commentator_id
        self.license = "cc0"
        self.version_title = ""
        self.deep_link = ""


def test_all_53_templates_have_english_companions_and_manifests():
    templates_dir = _REPO_DIR / "lessons" / "templates"
    folders = sorted([d for d in templates_dir.iterdir() if d.is_dir()])
    assert len(folders) == 53, f"Expected 53 template folders, found {len(folders)}"

    for d in folders:
        manifest_path = d / "manifest.yaml"
        assert manifest_path.exists(), f"Missing manifest.yaml in {d.name}"
        m = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))

        assert "title_en" in m and m["title_en"], f"Missing title_en in {d.name}"
        assert "files_en" in m and isinstance(m["files_en"], dict), f"Missing files_en in {d.name}"

        files_en = m["files_en"]
        assert "lesson_flow" in files_en, f"Missing lesson_flow in files_en for {d.name}"
        assert "full_lesson" in files_en, f"Missing full_lesson in files_en for {d.name}"

        # Verify actual files on disk
        lf_file = d / files_en["lesson_flow"]
        fl_file = d / files_en["full_lesson"]
        assert lf_file.is_file(), f"Missing {lf_file} on disk for {d.name}"
        assert fl_file.is_file(), f"Missing {fl_file} on disk for {d.name}"

        # Verify content has English headers and tags
        lf_content = lf_file.read_text(encoding="utf-8")
        assert "# Lesson Flow" in lf_content, f"Expected '# Lesson Flow' in {lf_file}"
        assert "[S#" in lf_content or "[S1]" in lf_content or "[S2]" in lf_content, f"Expected [S#] tags in {lf_file}"

        fl_content = fl_file.read_text(encoding="utf-8")
        assert ("# Full Lesson" in fl_content or "— Lesson for" in fl_content or "# Responsa" in fl_content), (
            f"Expected English heading in {fl_file}"
        )


def test_attach_template_bodies_hebrew_vs_english():
    # Test for gemara-iyun
    payload_he = {
        "id": "gemara-iyun",
        "dir": "lessons/templates/gemara-iyun",
        "files": {
            "source_sheet": "TEMPLATE_source_sheet.md",
            "lesson_flow": "TEMPLATE_lesson_flow.md",
            "full_lesson": "TEMPLATE_full_lesson.md",
        },
        "files_en": {
            "source_sheet": "TEMPLATE_source_sheet.md",
            "lesson_flow": "TEMPLATE_lesson_flow_en.md",
            "full_lesson": "TEMPLATE_full_lesson_en.md",
        },
    }
    _attach_template_bodies(payload_he, lang="he")
    assert "_lesson_flow" in payload_he
    assert "מהלך השיעור" in payload_he["_lesson_flow"]
    assert "שיעור מלא" in payload_he["_full_lesson"]

    payload_en = {
        "id": "gemara-iyun",
        "dir": "lessons/templates/gemara-iyun",
        "files": {
            "source_sheet": "TEMPLATE_source_sheet.md",
            "lesson_flow": "TEMPLATE_lesson_flow.md",
            "full_lesson": "TEMPLATE_full_lesson.md",
        },
        "files_en": {
            "source_sheet": "TEMPLATE_source_sheet.md",
            "lesson_flow": "TEMPLATE_lesson_flow_en.md",
            "full_lesson": "TEMPLATE_full_lesson_en.md",
        },
    }
    _attach_template_bodies(payload_en, lang="en")
    assert "_lesson_flow" in payload_en
    assert "Lesson Flow" in payload_en["_lesson_flow"]
    assert "Full Lesson" in payload_en["_full_lesson"]
    assert "מהלך השיעור" not in payload_en["_lesson_flow"]


def test_attach_template_bodies_fallback_to_disk_when_files_en_missing():
    # Even if files_en is not present in payload, lang="en" checks TEMPLATE_*_en.md on disk
    payload = {
        "id": "school-gemara-iyun-a-c",
        "dir": "lessons/templates/school-gemara-iyun-a-c",
        "files": {
            "source_sheet": "TEMPLATE_source_sheet.md",
            "lesson_flow": "TEMPLATE_lesson_flow.md",
            "full_lesson": "TEMPLATE_full_lesson.md",
        },
    }
    _attach_template_bodies(payload, lang="en")
    assert "_lesson_flow" in payload
    assert "Lesson Flow" in payload["_lesson_flow"]
    assert "Grades 1–3" in payload["_lesson_flow"]


def test_lesson_job_md_english_school_guidance_and_length():
    hits = [DummyHit(ref="Bava_Metzia.21a.1", text_en="Despair without awareness", text_he="יאוש שלא מדעת")]
    tpl = {
        "title": "עיון תלמודי",
        "title_en": "Talmudic Analysis (Iyun) — Grades 4–6 (Upper Elementary)",
        "structure": "העמדה → חקירה → ראשונים",
        "structure_en": "Framing → Inquiry → Rishonim",
        "_full_lesson": "# [Lesson Topic] — Lesson for Grades 4–6\n\nContent here.",
    }

    job = _lesson_job_md(
        "Lost objects and despair",
        hits,
        lang="en",
        audience="school",
        grade_band="d-f",
        length="medium",
        tpl=tpl,
        history=[],
    )

    # Check language and audience
    assert "lang: en" in job
    assert "## AUDIENCE\nSchool — grades d-f." in job
    assert _BAND_PED_EN["d-f"] in job

    # Check length formatting in English
    assert "## LENGTH\nMedium — approx" in job
    assert "Target word count for the full lesson: **1600–2400 words**" in job

    # Check template in English
    assert "Talmudic Analysis (Iyun) — Grades 4–6 (Upper Elementary) — Structure: Framing → Inquiry → Rishonim" in job
    assert "TEMPLATE SKELETON" in job

    # Check source ID
    assert "source ID: Bava_Metzia.21a.1" in job

    # Check instructions for English
    assert "LESSON_FLOW — a timed CLASSROOM plan for grade band d-f" in job
    assert "FULL_LESSON — the full lesson WRITTEN OUT in age-appropriate English prose" in job


def test_lesson_job_md_english_yeshiva():
    hits = [DummyHit(ref="Berakhot.2a.1", text_en="From what time may one recite the Shema in the evening?", text_he="מאימתי קורין את שמע בערבין")]
    tpl = {
        "title": "עיון תלמודי",
        "title_en": "Talmudic Analysis (Lamdanut) — Beit Midrash Scaffold",
        "structure": "העמדת הסוגיה → חקירה",
        "structure_en": "Framing the Sugya → Conceptual Inquiry",
        "_full_lesson": "# Full Lesson — [The Sugya in Depth]\n\nIntro",
    }

    job = _lesson_job_md(
        "Recitation of Shema",
        hits,
        lang="en",
        audience="yeshiva",
        grade_band=None,
        length="long",
        tpl=tpl,
        history=[],
    )

    assert "lang: en" in job
    assert "Beit Midrash / Yeshiva — adult learners; in-depth study." in job
    assert "Long — approx 75–90 min" in job
    assert "Target word count for the full lesson: **3000–4500 words**" in job
    assert "Talmudic Analysis (Lamdanut) — Beit Midrash Scaffold" in job
    assert "FULL_LESSON — a full beit-midrash shiur written out in depth in English" in job


def test_source_sheet_entry_english_prioritization():
    c = CitationOut(
        ref="Berakhot 2a",
        ref_he="ברכות ב ע״א",
        text_he="מאימתי קורין את שמע בערבין",
        text_en="From when may one recite the Shema in the evening?",
        commentator="",
        deep_link="",
        license="cc0",
        version_title="",
    )

    # In English, prefers English text and bilingual header
    entry_en = _source_sheet_entry(1, c, lang="en")
    assert "**1. Berakhot 2a (ברכות ב ע״א)**" in entry_en
    assert "From when may one recite the Shema in the evening?" in entry_en
    assert "מאימתי קורין" not in entry_en

    # In Hebrew, prefers Hebrew text and Hebrew header
    entry_he = _source_sheet_entry(1, c, lang="he")
    assert "**1. ברכות ב ע״א**" in entry_he
    assert "מאימתי קורין את שמע בערבין" in entry_he
    assert "From when may one" not in entry_he


def test_source_sheet_entry_english_fallback_to_hebrew_when_no_english():
    c = CitationOut(
        ref="Minchat Chinukh 1",
        ref_he="מנחת חינוך א",
        text_he="מצוה זו נוהגת בכל מקום",
        text_en="",
        commentator="",
        deep_link="",
        license="cc0",
        version_title="",
    )

    entry_en = _source_sheet_entry(1, c, lang="en")
    assert "**1. Minchat Chinukh 1 (מנחת חינוך א)**" in entry_en
    assert "מצוה זו נוהגת בכל מקום" in entry_en
