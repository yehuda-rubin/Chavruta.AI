"""Unit tests for conversational acknowledgement fast-path and מודגש prefix stripping."""

from __future__ import annotations

import pytest

from app.api import _run_query
from chavruta.generation.grounded import strip_mudgash_label
from chavruta.intents.llm_planner import distill_query
from chavruta.intents.router import is_conversational_acknowledgement


@pytest.mark.parametrize(
    "text",
    [
        "תודה",
        "תודה רבה",
        "תודה רבה!",
        "תודה לך",
        "תודה רבה לך",
        "תודה אגיד לו שצדקתי",
        "תודה, אגיד לו שצדקתי",
        "תודה! אגיד לו שצדקתי",
        "תודה אגיד לו",
        "תודה אומר לו",
        "תודה עזרת לי מאוד",
        "מעולה תודה",
        "מעולה, תודה רבה",
        "אחלה תודה",
        "סבבה תודה",
        "הבנתי תודה",
        "הבנתי, תודה רבה",
        "אוקיי תודה",
        "בסדר גמור תודה",
        "יישר כוח",
        "יישר כח",
        "יישר כוחך",
        "חזק וברוך",
        "שכוייח",
        "חן חן",
        "thanks",
        "thank you",
        "thank you very much",
        "great thanks",
        "got it thanks",
    ],
)
def test_conversational_acknowledgements_detected(text: str):
    assert is_conversational_acknowledgement(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "תודה אבל מה המקור לזה?",
        "תודה ומה לגבי בשר עוף?",
        "תודה תסביר לי עוד על דברי רש\"י",
        "האם מותר לאכול חזיר בפסח",
        "שלום אני וחבר שלי דנים בשאלה הבאה",
        "למה אסור לאכול חמץ בפסח",
        "מה הדין במי ששכח",
        "איך מכינים חלות לשבת",
        "שלום",
        "בוקר טוב",
        "",
        "   ",
    ],
)
def test_substantive_or_unrelated_not_acknowledgement(text: str):
    assert is_conversational_acknowledgement(text) is False


def test_strip_mudgash_label():
    assert strip_mudgash_label("מודגש אין היתר לאכול חזיר בפסח") == "אין היתר לאכול חזיר בפסח"
    assert strip_mudgash_label("**מודגש**: אין היתר לאכול חזיר") == "אין היתר לאכול חזיר"
    assert strip_mudgash_label("מודגש: אין היתר") == "אין היתר"
    assert strip_mudgash_label("**מודגש** איסור אכילת חזיר") == "איסור אכילת חזיר"
    assert strip_mudgash_label("אין היתר לאכול חזיר בפסח") == "אין היתר לאכול חזיר בפסח"
    assert strip_mudgash_label("") == ""


def test_run_query_fast_path_acknowledgement_hebrew():
    resp = _run_query("תודה אגיד לו שצדקתי", "he", "qa", [])
    assert resp.citations == []
    assert resp.grounded is False
    assert resp.intent == "qa"
    assert resp.files == []
    assert "בשמחה רבה!" in resp.answer
    assert "בהצלחה בדיון" in resp.answer


def test_run_query_fast_path_acknowledgement_general_hebrew():
    resp = _run_query("תודה רבה!", "he", "qa", [])
    assert resp.citations == []
    assert resp.grounded is False
    assert resp.intent == "qa"
    assert resp.files == []
    assert "בשמחה רבה!" in resp.answer


def test_run_query_fast_path_acknowledgement_english():
    resp = _run_query("Thank you very much!", "en", "qa", [])
    assert resp.citations == []
    assert resp.grounded is False
    assert resp.intent == "qa"
    assert resp.files == []
    assert "welcome" in resp.answer.lower()


def test_distill_query_preserves_acknowledgement():
    class DummyTurn:
        role = "user"
        text = "האם מותר לאכול חזיר בפסח?"

    distilled = distill_query("תודה אגיד לו שצדקתי", history=[DummyTurn()])
    assert distilled == "תודה אגיד לו שצדקתי"


def test_strip_control_codes():
    from chavruta.intents.llm_planner import strip_control_codes

    assert strip_control_codes("HHH שלום וברכה!") == "שלום וברכה!"
    assert strip_control_codes("[HHH] בשמחה רבה!") == "בשמחה רבה!"
    assert strip_control_codes("XXX דף מקורות") == "דף מקורות"
    assert strip_control_codes("XXX YYY מהלך השיעור ודף מקורות") == "מהלך השיעור ודף מקורות"
    assert strip_control_codes("ZZZ: שיעור שלם") == "שיעור שלם"
    assert strip_control_codes("NNN שאלה בהלכה") == "שאלה בהלכה"
    assert strip_control_codes("טקסט רגיל ללא קידוד") == "טקסט רגיל ללא קידוד"
    assert strip_control_codes("") == ""


def test_parse_distiller_output():
    from chavruta.intents.llm_planner import parse_distiller_output

    # Chitchat
    res = parse_distiller_output("HHH בשמחה רבה! שמחתי לעזור.", "תודה אגיד לו שצדקתי")
    assert res.action == "chitchat"
    assert "בשמחה רבה!" in res.answer
    assert "HHH" not in res.answer

    # Single file (Sources)
    res = parse_distiller_output("XXX דף מקורות על הלכות שבת", "תכין לי דף מקורות על שבת")
    assert res.action == "study"
    assert res.requested_files == ["sources"]
    assert res.distilled_query == "דף מקורות על הלכות שבת"
    assert "XXX" not in res.distilled_query

    # Two files combined with space (Sources + Flow)
    res = parse_distiller_output("XXX YYY מהלך שיעור ודף מקורות על קידושין", "תכין לי מהלך ודף מקורות")
    assert res.action == "study"
    assert res.requested_files == ["sources", "flow"]
    assert res.distilled_query == "מהלך שיעור ודף מקורות על קידושין"
    assert "XXX" not in res.distilled_query
    assert "YYY" not in res.distilled_query

    # All files (ZZZ)
    res = parse_distiller_output("ZZZ סוגיית תנורו של עכנאי", "שיעור מלא על תנורו של עכנאי")
    assert res.action == "study"
    assert res.requested_files == ["sources", "flow", "full"]
    assert res.distilled_query == "סוגיית תנורו של עכנאי"

    # No files (NNN)
    res = parse_distiller_output("NNN איסור אכילת חזיר בפסח", "האם מותר לאכול חזיר בפסח?")
    assert res.action == "study"
    assert res.requested_files == []
    assert res.distilled_query == "איסור אכילת חזיר בפסח"

    # Model omitted prefix code
    res = parse_distiller_output("איסור אכילת חזיר בפסח", "האם מותר לאכול חזיר בפסח?")
    assert res.action == "study"
    assert res.requested_files == []
    assert res.distilled_query == "איסור אכילת חזיר בפסח"


def test_classify_and_distill_mock():
    from chavruta.intents.llm_planner import classify_and_distill

    class MockChoice:
        def __init__(self, content):
            self.message = type("Message", (), {"content": content})()

    class MockResp:
        def __init__(self, content):
            self.choices = [MockChoice(content)]
            self.usage = type("Usage", (), {"prompt_tokens": 10, "completion_tokens": 10})()

    class MockCompletions:
        def __init__(self, content):
            self.content = content

        def create(self, **kwargs):
            return MockResp(self.content)

    class MockClient:
        def __init__(self, content):
            self.chat = type("Chat", (), {"completions": MockCompletions(content)})()

    # Test chitchat return
    res_chitchat = classify_and_distill("מי פיתח אותך?", client=MockClient("HHH פותחתי על ידי צוות חברותא."))
    assert res_chitchat.action == "chitchat"
    assert res_chitchat.answer == "פותחתי על ידי צוות חברותא."

    # Test two-file combination
    res_files = classify_and_distill(
        "דף מקורות ומהלך על קידושין",
        client=MockClient("XXX YYY סוגיית קידושין")
    )
    assert res_files.action == "study"
    assert res_files.requested_files == ["sources", "flow"]
    assert res_files.distilled_query == "סוגיית קידושין"


def test_lesson_file_filtering_by_target_files():
    from app.api import _generate_lesson_from_hits

    class MockBridgeLLM:
        def request(self, prompt, **kwargs):
            # Return lesson format with all 3 parts
            return (
                "===SOURCE_SHEET===\n[S1] מקור לדוגמה\n"
                "===LESSON_FLOW===\nשלב ראשון במהלך השיעור\n"
                "===FULL_LESSON===\nגוף השיעור המלא והמורחב\n",
                []
            )

    class MockHit:
        ref = "Berakhot.2a"
        text = "מאימתי קורין את שמע"
        license = "CC-BY-SA"
        version_title = "Sefaria"
        commentator_id = None
        deep_link = ""

    hits = [MockHit()]

    # Request only sources and flow (XXX YYY)
    resp = _generate_lesson_from_hits(
        topic="קריאת שמע",
        hits=hits,
        lang="he",
        he=True,
        audience="yeshiva",
        grade_band="",
        length="medium",
        tpl={"id": "std"},
        history=[],
        owner_id="local",
        llm=MockBridgeLLM(),
        target_files=["sources", "flow"],
    )

    assert len(resp.files) == 2
    names = [f.name for f in resp.files]
    assert "דף_מקורות.doc" in names
    assert "מהלך_השיעור.doc" in names
    assert "השיעור_המלא.doc" not in names
