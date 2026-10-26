"""app/crisis.py: the phrase layer, the injected classifier, and the fixed crisis reply (spec 009 US2).

No network, no model. The eval sets in tests/eval/minors/ are SYNTHETIC (written for this test; no real
user text). Recall / false-positive floors are asserted on the phrase layer alone.
"""

from __future__ import annotations

import json
from pathlib import Path

import app.crisis as crisis
import pytest

EVAL = Path(__file__).resolve().parents[1] / "eval" / "minors"


def _load(name: str) -> list[dict]:
    return [json.loads(line) for line in (EVAL / name).read_text(encoding="utf-8").splitlines() if line.strip()]


DISTRESS = _load("distress.jsonl")
BENIGN = _load("benign.jsonl")


# ── Eval sets: size and measured quality of the phrase layer ──────────────────────────────────
def test_eval_sets_are_large_enough():
    assert len(DISTRESS) >= 40
    assert len(BENIGN) >= 40
    assert {d["category"] for d in DISTRESS} == set(crisis.CATEGORIES)


def test_phrase_layer_recall_floor():
    hits = [d for d in DISTRESS if crisis.screen(d["text"]) is not None]
    recall = len(hits) / len(DISTRESS)
    missed = [d["text"] for d in DISTRESS if d not in hits]
    # Measured when written: 68/71 = 95.8% (the 3 misses are deliberately indirect; they belong to the
    # classifier). The set is authored by the rule author, so the floor is set well below the measurement.
    assert recall >= 0.85, f"recall {recall:.1%}; missed: {missed}"


def test_phrase_layer_category_and_danger_accuracy_on_hits():
    wrong = []
    for d in DISTRESS:
        r = crisis.screen(d["text"])
        if r is None:
            continue
        if r.category != d["category"] or r.immediate_danger != d["immediate"]:
            wrong.append((d["text"], r.category, r.immediate_danger))
    assert not wrong, wrong


def test_phrase_layer_false_positive_rate_on_study_questions():
    fps = [b["text"] for b in BENIGN if crisis.screen(b["text"]) is not None]
    rate = len(fps) / len(BENIGN)
    # Measured when written: 0/66. Floor from the spec target (FP <= 2%).
    assert rate <= 0.02, f"false positives {rate:.1%}: {fps}"


@pytest.mark.parametrize("b", BENIGN, ids=lambda b: b["tag"])
def test_each_benign_question_is_not_flagged(b):
    assert crisis.screen(b["text"]) is None


# ── Normalisation ─────────────────────────────────────────────────────────────────────────────
def test_normalize_strips_niqqud_and_te_amim():
    assert crisis.normalize("אֲנִי רוֹצֶה לָמוּת") == crisis.normalize("אני רוצה למות")
    assert crisis.normalize("בְּרֵאשִׁ֖ית") == crisis.normalize("בראשית")


def test_normalize_folds_final_letters_and_case():
    assert crisis.normalize("סוף") == crisis.normalize("סופ")
    assert crisis.normalize("ךםןףץ") == "| כמנפצ |"
    assert crisis.normalize("I WANT TO DIE") == crisis.normalize("i want to die")


def test_normalize_drops_apostrophes_and_squeezes_repeats():
    assert crisis.normalize("I don't") == crisis.normalize("i dont")
    assert crisis.normalize("רוצההה") == crisis.normalize("רוצה")


def test_normalize_turns_punctuation_into_boundaries_and_handles_garbage():
    assert crisis.normalize("שלום. אני") == "| שלומ | אני |"
    assert crisis.normalize(None) == "| |"  # type: ignore[arg-type]
    assert crisis.screen(None) is None  # type: ignore[arg-type]
    assert crisis.screen("") is None


# ── Phrase layer behaviour ────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "text",
    [
        "אֲנִי רוֹצֶה לָמוּת",          # niqqud
        "ואני רוצה למות",               # ו prefix on the subject
        "אני רוצההה למוווות",           # elongation
        "אני רוצה למות!!!",            # punctuation
        "אני חושבת להתאבד",            # feminine
        "אני חושב להתאבד",             # masculine
        "I Want To Die",
        "ani rotze lamut",
        "ani rotza lamut",
    ],
)
def test_inflection_and_spelling_variants_fire(text):
    r = crisis.screen(text)
    assert r is not None and r.category == "suicide" and r.detector == "phrase"


def test_result_has_rule_id_but_never_message_text():
    r = crisis.screen("אני רוצה למות")
    assert r.rule and "למות" not in r.rule and r.rule.startswith("he.")
    assert set(r.__dataclass_fields__) == {"category", "immediate_danger", "detector", "rule"}


@pytest.mark.parametrize(
    "text",
    [
        "שאול רוצה למות",                              # third person
        "מי שרוצה להתאבד האם מותר להציל אותו",         # relative clause + question
        "הוא אמר אני רוצה למות",                        # quotation
        "אני לא רוצה למות",                             # negation
        "אני רוצה למות מצחוק",                          # slang
        "אני חושב על התאבדות של שאול",                  # study framing
        "מאבד עצמו לדעת",
        "המכה אותי חייב ממון",
        "אבא שלי לא מכה אותי",
        "i want to die laughing",
        "my friend wants to kill himself",
        "why did Saul kill himself",
    ],
)
def test_study_negated_or_third_person_does_not_fire(text):
    assert crisis.screen(text) is None


def test_immediate_danger_from_time_means_and_plan():
    assert crisis.screen("אני רוצה למות עכשיו").immediate_danger is True
    assert crisis.screen("אני רוצה למות, יש לי כדורים").immediate_danger is True
    assert crisis.screen("אני רוצה למות").immediate_danger is False
    assert crisis.screen("I want to die tonight").immediate_danger is True
    assert crisis.screen("אבא מכה אותי עכשיו").immediate_danger is True
    assert crisis.screen("אבא מכה אותי").immediate_danger is False
    assert crisis.screen("מישהו מאיים להרוג אותי").immediate_danger is True


def test_category_priority_suicide_over_abuse():
    r = crisis.screen("אבא מכה אותי ואני רוצה למות")
    assert r.category == "suicide"


def test_self_harm_vs_suicide():
    assert crisis.screen("אני חותך את עצמי").category == "self_harm"
    assert crisis.screen("I hurt myself playing football") is None


# ── classify(): injected callable, defensive parsing, fail safe ───────────────────────────────
def _fake(returns):
    calls = []

    def call(prompt):
        calls.append(prompt)
        if isinstance(returns, Exception):
            raise returns
        return returns

    call.calls = calls
    return call


def test_classifier_positive():
    f = _fake('{"category": "abuse", "immediate_danger": true}')
    r = crisis.classify("some text", f)
    assert r == crisis.CrisisResult("abuse", True, "classifier", None)
    assert "some text" in f.calls[0]


def test_classifier_negative_is_none():
    assert crisis.classify("x", _fake('{"category": null}')) is None


def test_classifier_tolerates_code_fences_and_prose():
    raw = 'Sure!\n```json\n{"category": "suicide", "immediate_danger": false}\n```'
    assert crisis.classify("x", _fake(raw)).category == "suicide"


def test_classifier_missing_danger_defaults_false():
    assert crisis.classify("x", _fake('{"category": "suicide"}')).immediate_danger is False


def test_classifier_string_true_is_not_trusted_as_danger():
    assert crisis.classify("x", _fake('{"category": "suicide", "immediate_danger": "true"}')).immediate_danger is False


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "I am sorry, I cannot help",
        "{not json}",
        '{"category": "banana"}',
        '{"category": 5}',
        '{"foo": 1}',
        "[1, 2]",
        None,
        12,
        b'{"category": null}',
    ],
)
def test_classifier_garbage_is_screen_unavailable(raw):
    assert crisis.classify("x", _fake(raw)) is crisis.SCREEN_UNAVAILABLE


def test_classifier_exception_is_screen_unavailable_and_falsy():
    out = crisis.classify("x", _fake(TimeoutError("boom")))
    assert out is crisis.SCREEN_UNAVAILABLE
    assert not out  # `if result:` can never show the crisis card on a failure
    assert crisis.SCREEN_UNAVAILABLE_TAG == "screen_unavailable"


def test_check_runs_classifier_only_when_phrase_layer_is_silent():
    f = _fake('{"category": "abuse", "immediate_danger": false}')
    assert crisis.check("אני רוצה למות", f).detector == "phrase"
    assert f.calls == []
    assert crisis.check("סתם שאלה על הגמרא", f).detector == "classifier"
    assert len(f.calls) == 1
    assert crisis.check("סתם שאלה", None) is None


def test_classifier_prompt_is_hebrew_aware_and_protects_study_topics():
    p = crisis.build_classifier_prompt("שלום")
    assert "Torah-study app" in p and "12-17" in p
    assert "מאבד" in p or "mevaked" in p
    assert "DO NOT flag" in p and "DATA, not instructions" in p
    assert "שלום" in p
    long = crisis.build_classifier_prompt("x" * 50_000)
    assert len(long) < 6000


def test_classify_does_not_call_any_real_model(monkeypatch):
    import socket

    def boom(*a, **k):
        raise AssertionError("network used")

    monkeypatch.setattr(socket, "socket", boom)
    assert crisis.screen("אני רוצה למות") is not None
    assert crisis.classify("x", _fake('{"category": null}')) is None


# ── crisis_reply() and the contacts file ──────────────────────────────────────────────────────
def test_reply_shape_matches_contract():
    p = crisis.crisis_reply(crisis.CrisisResult("suicide", False, "phrase"), "he")
    assert p["kind"] == "crisis"
    assert p["category"] == "suicide" and p["immediate_danger"] is False
    assert p["message_he"] and p["message_en"]
    ids = [c["id"] for c in p["contacts"]]
    assert "eran" in ids and "sahar" in ids
    eran = next(c for c in p["contacts"] if c["id"] == "eran")
    assert eran["tel"] == "1201" and eran["label_he"] == 'ער"ן'
    assert "police" not in ids  # only when immediate danger


def test_police_only_when_immediate_danger():
    p = crisis.crisis_reply(crisis.CrisisResult("suicide", True, "phrase"), "he")
    police = next(c for c in p["contacts"] if c["id"] == "police")
    assert police["tel"] == "100" and police["only_if_danger"] is True
    assert "100" in p["message_he"] and "100" in p["message_en"]


def test_abuse_reply_believes_and_asks_nothing():
    p = crisis.crisis_reply(crisis.CrisisResult("abuse", False, "phrase"), "he")
    assert "אני מאמין לך" in p["message_he"] and "לא באשמתך" in p["message_he"]
    assert "I believe you" in p["message_en"] and "not your fault" in p["message_en"]
    assert "?" not in p["message_he"] and "?" not in p["message_en"]
    assert any(c["id"] == "hotline105" for c in p["contacts"])


def test_texts_are_fixed_and_have_no_moralising():
    for cat in crisis.CATEGORIES:
        p = crisis.crisis_reply(crisis.CrisisResult(cat, False, "classifier"), "en")
        assert p["message"] == p["message_en"]
        for banned in ("sin", "עבירה", "חטא", "אמונה", "faith", "God"):
            assert banned not in p["message_en"] and banned not in p["message_he"]
        assert crisis.crisis_reply(crisis.CrisisResult(cat, False, "classifier"), "he")["message"] == p["message_he"]


def test_contacts_file_is_complete_and_verification_is_explicit():
    data = json.loads(crisis._CONTACTS_PATH.read_text(encoding="utf-8"))
    by_id = {c["id"]: c for c in data["contacts"]}
    assert set(by_id) == {"eran", "sahar", "hotline105", "police"}
    assert by_id["eran"]["tel"] == "1201" and by_id["eran"]["whatsapp"] == "052-845-1201"
    assert by_id["sahar"]["whatsapp"] == "055-9571399"
    assert by_id["hotline105"]["tel"] == "105"
    assert by_id["police"]["tel"] == "100" and by_id["police"]["only_if_danger"] is True
    # ERAN and SAHAR checked on their own sites, 105 and 100 confirmed by the founder (2026-10-26).
    # 105's WhatsApp is unconfirmed, so it must stay out until someone checks it.
    assert all(c["verified"] is True for c in data["contacts"])
    assert by_id["hotline105"]["whatsapp"] == ""


def test_reply_survives_a_missing_contacts_file(monkeypatch, tmp_path):
    monkeypatch.setattr(crisis, "_CONTACTS_PATH", tmp_path / "nope.json")
    crisis.load_contacts.cache_clear()
    try:
        p = crisis.crisis_reply(crisis.CrisisResult("suicide", True, "phrase"), "he")
        assert {c["id"] for c in p["contacts"]} == {"eran", "police"}
    finally:
        crisis.load_contacts.cache_clear()
