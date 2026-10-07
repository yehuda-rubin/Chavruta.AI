import pytest
from chavruta.pipeline.pipeline import _detect_lang, ChavrutaPipeline
from chavruta.corpus.schema import Intent
from chavruta.retrieval.base import Query, RankedHit
from chavruta.generation.grounded import _quote_skeleton, unverified_quotes
from app.email_pool import render_auth_email
from app.api import _chavruta_job_md, CitationOut


def test_detect_lang_english_with_hebrew_word():
    text = "What does רש״י say about Genesis 1:1?"
    assert _detect_lang(text) == "en"

    text2 = "How does Rambam (רמב״ם) explain this mitzvah?"
    assert _detect_lang(text2) == "en"


def test_detect_lang_hebrew_dominated():
    text = "מה אומר רש״י על בראשית פרק א פסוק א?"
    assert _detect_lang(text) == "he"

    text2 = "שלום עליכם"
    assert _detect_lang(text2) == "he"


def test_resolve_query_respects_passed_lang():
    class DummyPipeline(ChavrutaPipeline):
        def __init__(self):
            self.router = None

    pipe = DummyPipeline()
    q = Query(text="מה אומר רש״י על בראשית?", lang="en", intent=Intent.QA)
    rq = pipe._resolve_query(q)
    assert rq.lang == "en"

    q2 = Query(text="What does Rashi say?", lang=None, intent=Intent.QA)
    rq2 = pipe._resolve_query(q2)
    assert rq2.lang == "en"

    q3 = Query(text="מה אומר רש״י?", lang=None, intent=Intent.QA)
    rq3 = pipe._resolve_query(q3)
    assert rq3.lang == "he"


def test_quote_skeleton_english():
    raw = "In the beginning, God created the heaven and the earth!"
    skel = _quote_skeleton(raw, lang="en")
    assert skel == "inthebeginninggodcreatedtheheavenandtheearth"

    # Hebrew mode preserves Hebrew characters and strips niqqud
    he_raw = "בְּרֵאשִׁ֖ית בָּרָ֣א אֱלֹהִ֑ים"
    he_skel = _quote_skeleton(he_raw, lang="he")
    assert he_skel == "בראשיתבראאלהים"


def test_unverified_quotes_english():
    source = RankedHit(
        chunk_id="c1",
        ref="Genesis.1.1",
        text="In the beginning God created the heavens and the earth.",
        text_en="In the beginning God created the heavens and the earth.",
        score=1.0,
    )
    # Verbatim quote present in source:
    answer = 'As stated in scripture: "In the beginning God created the heavens and the earth."'
    assert unverified_quotes(answer, [source], lang="en") == []

    # Fabricated quote not in source:
    fabricated = 'The text clearly says: "Thou shalt not ever eat shrimp under any circumstances whatsoever."'
    bad = unverified_quotes(fabricated, [source], lang="en")
    assert len(bad) > 0


def test_render_auth_email_english():
    # signup
    subj, html, text = render_auth_email("signup", "https://chavrutaai.org/verify", lang="en")
    assert subj == "Welcome to Chavruta AI — Confirm your email"
    assert "Confirm Email" in html
    assert 'dir="ltr"' in html
    assert 'lang="en"' in html
    assert "https://chavrutaai.org/verify" in html

    # recovery
    subj, html, text = render_auth_email("recovery", "https://chavrutaai.org/reset", lang="en")
    assert subj == "Reset your password — Chavruta AI"
    assert "Reset Password" in html

    # magiclink
    subj, html, text = render_auth_email("magiclink", "https://chavrutaai.org/login", lang="en")
    assert subj == "Your sign-in link — Chavruta AI"
    assert "Sign In" in html


def test_chavruta_job_md_english():
    md = _chavruta_job_md("Tell me about creation", [], lang="en", history=[])
    assert "## ROLE\nYou are **Chavruta** — a study partner learning together with the user at eye level, not lecturing from above." in md
    assert "Hold on — I didn't find the right source, please guide me" in md

    md_he = _chavruta_job_md("ספר לי על הבריאה", [], lang="he", history=[])
    assert "אתה **חברותא** לימודי" in md_he
    assert "רגע — לא עלה לי המקור הנכון, תכוון אותי" in md_he


def test_redeem_coupon_localized_plan_name():
    from unittest.mock import patch
    from app.api import redeem_coupon, RedeemRequest

    mock_res = {
        "kind": "plan",
        "plan": "pro",
        "until": "2026-12-31T23:59:59Z",
        "credits_added": 0,
        "credits_balance": 0,
        "mode": "grant",
    }
    with patch("app.api.coupons.redeem", return_value=mock_res):
        out_en = redeem_coupon(RedeemRequest(code="TESTCODE"), lang="en", owner="test_owner")
        assert out_en.plan_name == "Pro"

        out_he = redeem_coupon(RedeemRequest(code="TESTCODE"), lang="he", owner="test_owner")
        assert out_he.plan_name == "מלא"


def test_generate_chavruta_turn_preserves_text_en():
    from unittest.mock import MagicMock
    from app.api import _generate_chavruta_turn

    h = RankedHit(
        chunk_id="c1",
        ref="Genesis.1.1",
        text="בראשית ברא אלהים",
        text_en="In the beginning God created the heavens and the earth.",
        score=1.0,
    )
    llm_mock = MagicMock()
    llm_mock.request.return_value = ("According to [S1], God created everything.", [])

    turn = _generate_chavruta_turn(
        question="What does Genesis 1:1 say?",
        hits=[h],
        lang="en",
        he=False,
        history=[],
        weak=False,
        llm=llm_mock,
    )
    assert len(turn.citations) == 1
    assert turn.citations[0].text_en == "In the beginning God created the heavens and the earth."

