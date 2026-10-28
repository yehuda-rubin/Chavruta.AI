"""Pure unit tests for Spec 010 — Bagrut Exam Preparation Mode (מצב בגרויות).

Covers:
1. Curriculum configuration (`data/bagrut_curriculum.yaml`) & all 14 structural clean-room templates (`lessons/templates/bagrut-*/`).
2. Strict Zero-Retention Clean-Room verification (no copyrighted past Bagrut files on disk; templates contain `[ ]` placeholders).
3. Parameter detection & resolution (`detect_bagrut_subject`, `detect_bagrut_track`, `detect_bagrut_units`, `detect_bagrut_action`, `resolve_bagrut_params`, follow-up chat routing).
4. Unattached past exam blocking (`is_unattached_past_exam_query`).
5. Commentator & base-text hit boosting (`boost_bagrut_hits`).
6. Prompt & file builders (`build_bagrut_file_job_md`, `build_bagrut_chat_messages`, `split_bagrut_files`), minor safety injection, and Principle VIII advisory disclaimer.
7. End-to-end `_run_bagrut` and `_bagrut_turn_text` in `app/api.py` using deterministic mocks (zero real LLM or Qdrant calls).
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import yaml

from chavruta.bagrut import (
    load_bagrut_curriculum,
    detect_bagrut_subject,
    detect_bagrut_track,
    detect_bagrut_units,
    detect_bagrut_action,
    is_bagrut_file_rebuild_request,
    is_bagrut_narrow_topic_request,
    is_unattached_past_exam_query,
    resolve_bagrut_params,
    boost_bagrut_hits,
    split_bagrut_files,
    build_bagrut_file_job_md,
    build_bagrut_chat_messages,
)
from chavruta.corpus.audience import AudienceScope, use as use_audience
from chavruta.corpus.schema import Query, Turn

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = REPO_ROOT / "lessons" / "templates"

ALL_18_BAGRUT_TEMPLATES = [
    "bagrut-gemara-comprehensive",
    "bagrut-toshba-comprehensive",
    "bagrut-tanakh-comprehensive",
    "bagrut-machshava-comprehensive",
    "bagrut-tanakh-mmd-iyun",
    "bagrut-tanakh-mmd-bekiut",
    "bagrut-tanakh-mmd-torah-mitzvot",
    "bagrut-tanakh-mmd-neviim-shivat-tzion",
    "bagrut-tanakh-mamlachti-close",
    "bagrut-tanakh-mamlachti-themes",
    "bagrut-tanakh-unseen",
    "bagrut-gemara-sugya",
    "bagrut-gemara-rishonim",
    "bagrut-gemara-unseen",
    "bagrut-gemara-mavo-toshba",
    "bagrut-toshba-mishnah-halacha",
    "bagrut-toshba-case-study",
    "bagrut-toshba-thematic-halacha",
]
EXPECTED_14_TEMPLATES = ALL_18_BAGRUT_TEMPLATES


# ── 1. Curriculum & 14 Clean-Room Templates ──────────────────────────────────

def test_curriculum_yaml_loads_and_has_required_keys():
    curr = load_bagrut_curriculum()
    assert curr.get("version") == 1
    subjects = curr.get("subjects") or {}
    assert set(subjects.keys()) == {"tanakh", "gemara", "toshba", "machshava"}
    for subj_key, subj in subjects.items():
        assert subj.get("title_he") or subj.get("label_he"), f"{subj_key} missing Hebrew title"
        assert subj.get("title_en") or subj.get("label_en"), f"{subj_key} missing English title"
        assert subj.get("core_commentators"), f"{subj_key} missing core_commentators"
    aramaic = curr.get("aramaic_scaffold") or subjects["gemara"].get("aramaic_scaffold") or []
    assert len(aramaic) >= 12
    assert curr.get("rubric_principles_he")
    assert curr.get("rubric_principles_en")


def test_all_14_bagrut_templates_exist_and_have_valid_manifests():
    for tpl_name in EXPECTED_14_TEMPLATES:
        p = TEMPLATES_DIR / tpl_name
        assert p.is_dir(), f"Template directory missing: {tpl_name}"

    required_files = [
        "manifest.yaml",
        "TEMPLATE_exam.md",
        "TEMPLATE_exam_en.md",
        "TEMPLATE_rubric.md",
        "TEMPLATE_rubric_en.md",
        "TEMPLATE_summary.md",
        "TEMPLATE_summary_en.md",
    ]
    for tid in EXPECTED_14_TEMPLATES:
        tdir = TEMPLATES_DIR / tid
        for fname in required_files:
            fpath = tdir / fname
            assert fpath.is_file(), f"Missing {fname} in {tid}"
            content = fpath.read_text(encoding="utf-8")
            assert len(content.strip()) > 100, f"File {fpath} is unexpectedly short"
            if fname.startswith("TEMPLATE_"):
                assert "[" in content and "]" in content, f"{fpath} missing structural [ ] placeholders"

        manifest = yaml.safe_load((tdir / "manifest.yaml").read_text(encoding="utf-8"))
        assert manifest["id"] == tid
        assert manifest["mode"] == "bagrut"
        assert manifest["subject"] in {"tanakh", "gemara", "toshba", "machshava"}
        assert manifest["bagrut_track"] in {"mmd", "mamlachti", "both"}
        assert str(manifest["bagrut_units"]).strip()
        assert manifest.get("structure") or manifest.get("structure_he")
        assert manifest.get("structure_en")


def test_zero_retention_clean_room_no_raw_exam_files():
    """Verify no downloaded PDFs/DOCs of real Ministry of Education exams remain anywhere in the repo."""
    forbidden_patterns = ["*שאלון*בגרות*.pdf", "*mahvan*.pdf", "*2575*.pdf", "*5391*.pdf"]
    for pat in forbidden_patterns:
        matches = list(REPO_ROOT.rglob(pat))
        assert matches == [], f"Forbidden raw exam file found: {matches}"


# ── 2. Subject, Track, Units & Action Detection ──────────────────────────────

def test_detect_bagrut_subject():
    assert detect_bagrut_subject("תרגול בגרות בגמרא בבא מציעא דף ב") == "gemara"
    assert detect_bagrut_subject("סוגיית שניים אוחזין ואביי ורבא") == "gemara"
    assert detect_bagrut_subject("בגרות בתושב\"ע משנה והלכה שולחן ערוך") == "toshba"
    assert detect_bagrut_subject("בגרות בתנ\"ך שמואל א פרק טו") == "tanakh"


def test_detect_bagrut_track_and_units():
    assert detect_bagrut_track("בגרות בתנ\"ך חמ\"ד 5 יח\"ל") == "mmd"
    assert detect_bagrut_track("בגרות ממלכתי בתנ\"ך 2 יחידות") == "mamlachti"
    assert detect_bagrut_units("בגרות 3 יח\"ל") == "3"
    assert detect_bagrut_units("בגרות 2 יח\"ל") == "2"
    assert detect_bagrut_units("בגרות בתנ\"ך ללא ציון יחידות") == "5"


def test_detect_bagrut_action():
    assert detect_bagrut_action("תרגל איתי שאלת בגרות על מלכים א יח") == "practice"
    assert detect_bagrut_action("בדוק לי את התשובה לפי מחוון: תשובתי היא...") == "check"
    assert detect_bagrut_action("תכין לי סיכום מיקודית לבגרות על בראשית יב") == "summary"
    assert detect_bagrut_action("בנה לי מתכונת מלאה ומחוון בגמרא בבא מציעא") == "exam"
    assert detect_bagrut_action("תפתור את כל הבגרות הזאת ותחזיר לי את הפתרון כקובץ") == "solution"
    assert detect_bagrut_action("פתרון מלא לשאלון הבגרות בתנך") == "solution"


def test_resolve_bagrut_params_followup_after_file_routes_to_chat():
    history = [
        Turn(role="user", text="תכין מתכונת על שמואל א טו"),
        Turn(role="assistant", text="נוצרה מתכונת", bagrut=True),
    ]
    # Even if UI dropdown remains on "exam", a conversational follow-up question routes to "practice" (chat)
    params = resolve_bagrut_params(
        "אפשר להסביר יותר את שאלה 2 סעיף ב?",
        history=history,
        subject="tanakh",
        track="mmd",
        units="5",
        action="exam",
    )
    assert params["action"] == "practice"

    # Explicit rebuild request after a file turn stays on file generation
    assert is_bagrut_file_rebuild_request("תכין מתכונת חדשה על מלכים א יח") is True
    params_rebuild = resolve_bagrut_params(
        "תכין מתכונת חדשה על מלכים א יח",
        history=history,
        subject="tanakh",
        track="mmd",
        units="5",
        action="exam",
    )
    assert params_rebuild["action"] == "exam"


# ── 3. Unattached Past Exam Guardrail ────────────────────────────────────────

def test_is_unattached_past_exam_query():
    # Asking for a specific past exam question by year/season/questionnaire without attaching text -> blocked
    assert is_unattached_past_exam_query("מה התשובה לשאלה 4 בבגרות קיץ תשפ\"ג שאלון 2575?") is True
    assert is_unattached_past_exam_query("פתור לי את שאלה 2 ממועד חורף 2022") is True

    # If the user pasted or attached the question text -> allowed
    pasted = (
        "פתור לי את שאלה 2 ממועד קיץ תשפ\"ג:\n"
        "קרא את שמואל א פרק טו פסוקים א-לה. א. הסבר את טענת שאול בדבריו אל שמואל בפירוט רב על פי הפסוקים ורש\"י, "
        "והשווה לדברי שמואל בתשובתו המנומקת."
    )
    assert is_unattached_past_exam_query(pasted) is False

    # Normal topic requests -> allowed
    assert is_unattached_past_exam_query("בנה לי מתכונת על שמואל א פרק טו") is False


# ── 4. Commentator & Base-Text Boosting ──────────────────────────────────────

def _make_hit(ref: str, *, commentator_id: str | None = None, text: str = "טקסט בדיקה"):
    return SimpleNamespace(
        chunk_id=f"id_{ref}",
        work_id="test_work",
        ref=ref,
        base_ref="Genesis.12.1",
        lang="he",
        commentator_id=commentator_id,
        text=text,
        text_he=text,
        text_en="",
        deep_link="",
        license="CC-BY-SA",
        version_title="Masorah",
    )


def test_boost_bagrut_hits_orders_base_then_core_commentators():
    h_other = _make_hit("Other_ on Genesis.12.1", commentator_id="other_comm")
    h_rashi = _make_hit("Rashi on Genesis.12.1", commentator_id="rashi")
    h_base = _make_hit("Genesis.12.1", commentator_id=None)

    boosted = boost_bagrut_hits([h_other, h_rashi, h_base], "tanakh")
    assert boosted[0].ref == "Genesis.12.1"
    assert boosted[1].ref == "Rashi on Genesis.12.1"
    assert boosted[2].ref == "Other_ on Genesis.12.1"


# ── 5. Prompts, Minor Safety & File Splitting ────────────────────────────────

def test_build_bagrut_chat_messages_injects_minor_safety_and_toshba_disclaimer():
    hits = [_make_hit("Shulchan_Arukh,_Orach_Chayim.253.1", commentator_id=None)]
    params = {"subject": "toshba", "track": "mmd", "units": "5", "action": "practice"}

    with use_audience(AudienceScope(minor=True)):
        sys_prompt, usr_prompt = build_bagrut_chat_messages(
            "תרגל איתי שאלה על שהייה והטמנה בשבת",
            hits,
            "he",
            params=params,
        )
    # Principle VIII disclaimer for toshba
    assert "אינו פסק הלכה למעשה" in sys_prompt
    # Minor safety block from append_minor_safety
    assert "קטינים" in sys_prompt or "בטיחות" in sys_prompt or "תלמיד" in sys_prompt
    assert "Shulchan_Arukh,_Orach_Chayim.253.1" in usr_prompt


def test_split_bagrut_files_exam_and_rubric():
    raw = (
        "===BAGRUT_EXAM===\n"
        "# מתכונת בתנ\"ך\n\nתוכן המבחן [S1].\n\n"
        "===BAGRUT_RUBRIC===\n"
        "# מחוון למורה\n\nתוכן המחוון [S1].\n\n"
        "===ORDER===\n"
        "S1"
    )
    parts = split_bagrut_files(raw)
    assert "תוכן המבחן" in parts["BAGRUT_EXAM"]
    assert "תוכן המחוון" in parts["BAGRUT_RUBRIC"]
    assert parts["ORDER"] == "S1"


def test_build_bagrut_file_job_md_contains_template_and_sources():
    hits = [_make_hit("Genesis.12.1", commentator_id=None)]
    params = {"subject": "tanakh", "track": "mmd", "units": "5", "action": "exam"}
    job_md = build_bagrut_file_job_md(
        "לך לך בראשית יב",
        hits,
        "he",
        params=params,
        tpl={"title": "תבנית תנ\"ך", "structure": "פרק א-ג", "_exam": "# שלד מבחן [ ]", "_rubric": "# שלד מחוון [ ]"},
    )
    assert "===BAGRUT_EXAM===" in job_md
    assert "===BAGRUT_RUBRIC===" in job_md
    assert "Genesis.12.1" in job_md
    assert "# שלד מבחן [ ]" in job_md


# ── 6. End-to-End _run_bagrut in app/api.py ──────────────────────────────────

def test_run_bagrut_chat_and_exam_modes_with_mock_pipeline():
    import app.api as api

    hits = [
        _make_hit("Genesis.12.1", commentator_id=None, text="ויאמר ה' אל אברם לך לך מארצך"),
        _make_hit("Rashi on Genesis.12.1", commentator_id="rashi", text="לך לך - להנאתך ולטובתך"),
    ]
    mock_pipeline = MagicMock()
    mock_pipeline._resolve_query.side_effect = lambda q, history=None: Query(
        text=q.text, lang="he", named_refs=["Genesis.12.1"]
    )
    mock_pipeline.retriever.retrieve.return_value = SimpleNamespace(hits=hits, is_empty=False)
    mock_pipeline.retriever.base_sources_for_refs.return_value = [hits[0]]

    mock_llm = MagicMock()
    mock_llm.request.return_value = ("זוהי שאלת תרגול לבגרות על בראשית יב [S1] עם פירוש רש\"י [S2].", [])

    with patch.object(api, "_get_pipeline", return_value=mock_pipeline), \
         patch.object(api, "_select_bagrut_template", return_value=None):
        # 1) Practice mode (interactive chat — no files, empty lesson_id)
        res_chat = api._run_bagrut(
            "תרגל איתי שאלה על בראשית יב",
            "he",
            history=[],
            bagrut_subject="tanakh",
            bagrut_track="mmd",
            bagrut_units="5",
            bagrut_action="practice",
            owner_id="local",
            llm=mock_llm,
        )
        assert res_chat.intent == "bagrut"
        assert res_chat.grounded is True
        assert res_chat.files == []
        assert not res_chat.lesson_id
        assert len(res_chat.citations) == 2

        # 2) Unattached past exam query is blocked cleanly without calling LLM
        mock_llm.reset_mock()
        res_blocked = api._run_bagrut(
            "מה התשובה לשאלה 3 בבגרות קיץ תשפ\"ג שאלון 2575?",
            "he",
            history=[],
            bagrut_subject="tanakh",
            bagrut_track="mmd",
            bagrut_units="5",
            bagrut_action="practice",
            owner_id="local",
            llm=mock_llm,
        )
        assert res_blocked.grounded is False
        assert "אינם שמורים" in res_blocked.answer
        mock_llm.request.assert_not_called()

        # 3) Exam mode produces downloadable Word files for source sheet, exam, and rubric
        mock_llm.request.return_value = (
            "===BAGRUT_EXAM===\n"
            "# מתכונת בתנ\"ך — בראשית יב\n\nשאלה 1 על הפסוק [S1].\n\n"
            "===BAGRUT_RUBRIC===\n"
            "# מחוון\n\nתשובה מלאה [S1] ורש\"י [S2].\n\n"
            "===ORDER===\n"
            "S1, S2",
            [],
        )
        with patch.object(api.db, "save_lesson", return_value=None) as mock_save_lesson:
            res_exam = api._run_bagrut(
                "בנה מתכונת על בראשית יב",
                "he",
                history=[],
                bagrut_subject="tanakh",
                bagrut_track="mmd",
                bagrut_units="5",
                bagrut_action="exam",
                owner_id="local",
                llm=mock_llm,
            )
        assert res_exam.intent == "bagrut"
        assert res_exam.lesson_id
        mock_save_lesson.assert_called_once()
        file_names = [f.name for f in res_exam.files]
        assert "שאלון_מתכונת_לבגרות.doc" in file_names
        assert "מחוון_תשובות_וניקוד.doc" in file_names
        assert "דף_מקורות_לבגרות.doc" in file_names

        # 4) Verify _bagrut_turn_text detects saved Bagrut file turns for session continuation
        saved_msg = {
            "role": "assistant",
            "text": "",
            "intent": "bagrut",
            "files": [f.model_dump() for f in res_exam.files],
        }
        carried_text, is_bg = api._bagrut_turn_text(saved_msg)
        assert is_bg is True
        assert carried_text


def test_bagrut_topic_diversity_and_narrow_detection():
    # Narrow topic detection
    assert is_bagrut_narrow_topic_request("בנה מתכונת רק על מסכת בבא מציעא פרק ב") is True
    assert is_bagrut_narrow_topic_request("מתכונת בהלכות שבת בלבד") is True
    assert is_bagrut_narrow_topic_request("מתכונת ממוקדת על אישות") is True
    assert is_bagrut_narrow_topic_request("תבנה לי מתכונת בתושב\"ע") is False
    assert is_bagrut_narrow_topic_request("מתכונת לשאלון 5391") is False

    # Broad exam prompt includes curriculum diversity requirement
    broad_job = build_bagrut_file_job_md(
        "תבנה לי מתכונת בתושב\"ע",
        [],
        "he",
        params={"subject": "toshba", "track": "mmd", "units": "3", "action": "exam"},
    )
    assert "חובת פיזור נושאי ומגוון מקורות" in broad_job
    assert "Mandatory Curriculum Diversity" in broad_job

    # Narrow exam prompt instructs focus on the requested topic
    narrow_job = build_bagrut_file_job_md(
        "מתכונת רק על הלכות שבת",
        [],
        "he",
        params={"subject": "toshba", "track": "mmd", "units": "3", "action": "exam"},
    )
    assert "התמקדות בנושא המבוקש" in narrow_job

    # Verify template selection: comprehensive for broad exam, sugya/chapter for narrow
    from app import api
    tpl_broad = api._select_bagrut_template("תבנה לי מתכונת לבגרות בגמרא", "gemara", "mmd", "5")
    assert tpl_broad is not None
    assert tpl_broad["id"] == "bagrut-gemara-comprehensive"

    tpl_toshba_broad = api._select_bagrut_template("תבנה לי מתכונת בתושב\"ע", "toshba", "mmd", "5")
    assert tpl_toshba_broad is not None
    assert tpl_toshba_broad["id"] == "bagrut-toshba-comprehensive"

    tpl_narrow = api._select_bagrut_template("מתכונת על בבא מציעא פרק ב", "gemara", "mmd", "5")
    assert tpl_narrow is not None
    assert tpl_narrow["id"] in {"bagrut-gemara-sugya", "bagrut-gemara-rishonim"}
    assert tpl_narrow["id"] != "bagrut-gemara-comprehensive"


def test_dynamic_bagrut_curriculum_and_machshava():
    from chavruta.bagrut.engine import (
        detect_bagrut_subject,
        get_active_bagrut_curriculum,
        format_active_curriculum_prompt_block,
    )
    from app.db import (
        init_db,
        upsert_bagrut_curriculum_cache,
        get_active_bagrut_curriculum_from_db,
    )

    # 1. Machshevet Yisrael subject detection
    assert detect_bagrut_subject("תבנה לי מתכונת במחשבת ישראל") == "machshava"
    assert detect_bagrut_subject("שאלון מתכונת 281 על ספר הכוזרי") == "machshava"
    assert detect_bagrut_subject("עיקרי האמונה והרב קוק") == "machshava"

    # 2. Active curriculum resolution for Gemara
    curr = get_active_bagrut_curriculum("gemara")
    assert curr is not None
    assert curr.get("tractate") == "בבא בתרא" or curr.get("tractate_book") == "בבא בתרא"

    # 3. Dynamic DB cache upsert and lookup (Zero-deploy persistence)
    init_db()
    upsert_bagrut_curriculum_cache(
        subject="gemara",
        track="mmd",
        units=5,
        exam_code="5391_test",
        year_he='תשפ"ז_בדיקה',
        tractate_book="בבא בתרא",
        ref_prefix="Bava_Batra",
        chapter_he="פרק ראשון השותפין",
        daf_verses_he="ב. עד ד:",
        page_range=["2a", "2b", "3a", "3b", "4a", "4b"],
        key_topics=["מחיצה בחצר", "היזק ראיה"],
        canonical_queries=["בבא בתרא דף ב מחיצה בחצר"],
        source_url="https://meyda.education.gov.il",
        is_active=1,
    )

    db_curr = get_active_bagrut_curriculum_from_db("gemara", exam_code="5391_test")
    assert db_curr is not None
    assert db_curr["tractate_book"] == "בבא בתרא"
    assert db_curr["page_range"] == ["2a", "2b", "3a", "3b", "4a", "4b"]

    # 4. Prompt block formatting
    block = format_active_curriculum_prompt_block("gemara", "mmd", 5)
    assert any("MANDATORY ACTIVE MINISTRY OF EDUCATION CURRICULUM" in line for line in block)
    assert any("בבא בתרא" in line for line in block)

def test_bagrut_turn_text_history_resolution():
    from app.api import _bagrut_turn_text

    # Simulated message turn with 3 files: source sheet, exam, rubric
    turn_msg = {
        "text": "",
        "intent": "bagrut",
        "files": [
            {
                "name": "דף_מקורות_לבגרות.doc",
                "title": "דף מקורות לבגרות",
                "content": "בבא בתרא דף ב. מתני' השותפין שרצו לעשות מחיצה בחצר",
            },
            {
                "name": "שאלון_מתכונת_לבגרות.doc",
                "title": "שאלון מתכונת לבגרות",
                "content": "שאלה 1: סוגיית היזק ראיה\nא. פירוק המשנה\nב. זיהוי המחלוקת",
            },
            {
                "name": "מחוון_תשובות_וניקוד.doc",
                "title": "מחוון תשובות וניקוד",
                "content": "שאלה 1: תשובת מופת לסעיף א וסעיף ב",
            },
        ],
    }

    history_text, is_bagrut = _bagrut_turn_text(turn_msg)
    assert is_bagrut is True
    # Crucial check: history MUST contain the exam questions and rubric, NOT just the source sheet!
    assert "### שאלון הבחינה:" in history_text
    assert "שאלה 1: סוגיית היזק ראיה" in history_text
    assert "### מחוון תשובות וניקוד:" in history_text
    assert "שאלה 1: תשובת מופת" in history_text

def test_split_bagrut_files_hebrew_and_fallback():
    from chavruta.bagrut.engine import split_bagrut_files

    # 1. Delimiters written in Hebrew (as happened in production)
    hebrew_delims = """===שאלון מתכונת===
הנה שאלון הבגרות:
שאלה 1: פירוק המשנה
===מחוון בגרות===
מחוון תשובות וניקוד:
שאלה 1: תשובת מופת
===ORDER===
S1, S2"""

    res1 = split_bagrut_files(hebrew_delims)
    assert "שאלה 1: פירוק המשנה" in res1["BAGRUT_EXAM"]
    assert "מחוון בגרות" not in res1["BAGRUT_EXAM"]
    assert "שאלה 1: תשובת מופת" in res1["BAGRUT_RUBRIC"]
    assert res1["ORDER"] == "S1, S2"

    # 2. Embedded rubric fallback when delimiter was missing but heading is present
    embedded_rubric = """===BAGRUT_EXAM===
שאלה 1: שאלה בשאלון
שאלה 2: שאלה שניה

## מחוון תשובות וניקוד למורה
שאלה 1: פתרון
שאלה 2: פתרון"""

    res2 = split_bagrut_files(embedded_rubric)
    assert "שאלה 1: שאלה בשאלון" in res2["BAGRUT_EXAM"]
    assert "מחוון" not in res2["BAGRUT_EXAM"]
    assert "שאלה 1: פתרון" in res2["BAGRUT_RUBRIC"]

