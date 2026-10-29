"""Unit tests for Talmud attribution verification and auto-correction.

Pins the fix for the production bug where an answer quoted a Mishnah ("כפרו שניהן כאחת...")
and attributed it to Shevuot 33b instead of 31b.

All tests are pure and deterministic (no Qdrant, no LLM, no network).
"""

from __future__ import annotations

import pytest

from chavruta.generation import grounded, guards
from chavruta.generation.grounded import (
    MisattributedTalmud,
    misattributed_talmud_quotes,
    fix_misattributed_talmud_quotes,
)


class DummySource:
    def __init__(self, ref: str, text: str):
        self.ref = ref
        self.text = text
        self.text_he = text


# ── Test 1: Production regression — Shevuot 33b misattribution corrected to 31b ─

def test_production_regression_shevuot_33b_to_31b():
    sources = [
        DummySource("Shevuot.31b", 'כפרו שניהן כאחת שניהן חייבין בזה אחר זה הראשון חייב והשני פטור'),
        DummySource("Shevuot.33b", 'משביע אני עליכם אם לא תבואו ותעידו שאני כהן שאני לוי הרי אלו פטורין'),
    ]
    text = (
        'המשנה בדף לג,ב (משנה ד) עוסקת במקרה של שני עדים: '
        '"כפרו שניהן כאחת, שניהן חייבין. בזה אחר זה, הראשון חייב והשני פטור".'
    )

    findings = misattributed_talmud_quotes(text, sources)
    assert len(findings) == 1
    f = findings[0]
    assert f.stated_ref == "Shevuot.33b"
    assert f.found_in_ref == "Shevuot.31b"
    assert "כפרו שניהן" in f.quote

    fixed_text, fixed_findings = fix_misattributed_talmud_quotes(text, sources)
    assert len(fixed_findings) == 1
    assert 'בדף ל"א,ב' in fixed_text
    assert 'בדף לג,ב' not in fixed_text


# ── Test 2: Explicit tractate in the citation phrase ─────────────────────────

def test_explicit_tractate_in_attribution():
    sources = [
        DummySource("Shevuot.31b", 'כפרו שניהן כאחת שניהן חייבין בזה אחר זה הראשון חייב והשני פטור'),
        DummySource("Shevuot.33b", 'משביע אני עליכם אם לא תבואו ותעידו שאני כהן הרי אלו פטורין'),
    ]
    text = (
        'במסכת שבועות דף לג ע"ב מובאת ההלכה הבאה: '
        '"כפרו שניהן כאחת שניהן חייבין בזה אחר זה הראשון חייב והשני פטור".'
    )

    findings = misattributed_talmud_quotes(text, sources)
    assert len(findings) == 1
    assert findings[0].stated_ref == "Shevuot.33b"
    assert findings[0].found_in_ref == "Shevuot.31b"

    fixed_text, _ = fix_misattributed_talmud_quotes(text, sources)
    assert 'במסכת שבועות דף ל"א ע"ב' in fixed_text
    assert 'במסכת שבועות דף לג ע"ב' not in fixed_text


# ── Test 3: Correctly-attributed quote passes cleanly with zero changes ────────

def test_correct_talmud_attribution_passes_clean():
    sources = [
        DummySource("Shevuot.31b", 'כפרו שניהן כאחת שניהן חייבין'),
        DummySource("Shevuot.33b", 'משביע אני עליכם אם לא תבואו ותעידו שאני כהן שאני לוי שאיני בן גרושה הרי אלו פטורין'),
    ]
    text = (
        'במשנה בשבועות דף לג ע"ב נקבע: '
        '"משביע אני עליכם אם לא תבואו ותעידו שאני כהן שאני לוי שאיני בן גרושה הרי אלו פטורין".'
    )

    findings = misattributed_talmud_quotes(text, sources)
    assert findings == []

    fixed_text, fixed_findings = fix_misattributed_talmud_quotes(text, sources)
    assert fixed_findings == []
    assert fixed_text == text


# ── Test 4: Support for multiple Hebrew daf / amud notation formats ───────────

@pytest.mark.parametrize("input_phrase, expected_replaced_phrase", [
    ('בדף לג,ב', 'בדף ל"א,ב'),
    ('בדף לג ע"ב', 'בדף ל"א ע"ב'),
    ('בדף לג עמוד ב', 'בדף ל"א עמוד ב'),
    ('בדף לג:', 'בדף ל"א:'),
])
def test_various_hebrew_talmud_amud_formats(input_phrase, expected_replaced_phrase):
    sources = [
        DummySource("Bava_Metzia.31b", 'הרואה שודדין באים על שדה חבירו חייב להציל'),
        DummySource("Bava_Metzia.33b", 'אביו ורבו רבו קודם לאביו שאביו הביאו לעולם הזה'),
    ]
    text = f'הגמרא {input_phrase} אומרת: "הרואה שודדין באים על שדה חבירו חייב להציל".'

    findings = misattributed_talmud_quotes(text, sources)
    assert len(findings) == 1
    assert findings[0].found_in_ref == "Bava_Metzia.31b"
    assert findings[0].stated_ref == "Bava_Metzia.33b"

    fixed_text, _ = fix_misattributed_talmud_quotes(text, sources)
    assert expected_replaced_phrase in fixed_text


# ── Test 5: Guard telemetry integration ─────────────────────────────────────

def test_guards_reporting_integration(monkeypatch):
    recorded = []
    monkeypatch.setattr(guards, "_sink", lambda kind, intent, detail: recorded.append((kind, intent, detail)))

    sources = [
        DummySource("Shevuot.31b", 'כפרו שניהן כאחת שניהן חייבין בזה אחר זה'),
        DummySource("Shevuot.33b", 'משביע אני עליכם שאני כהן הרי אלו פטורין'),
    ]
    text = 'המשנה בדף לג,ב אומרת: "כפרו שניהן כאחת שניהן חייבין בזה אחר זה".'

    fixed_text, findings = fix_misattributed_talmud_quotes(text, sources)
    assert len(findings) == 1

    # Simulate pipeline reporting
    for tf in findings:
        guards.report("citation_mismatch", "qa",
                      {"quote": tf.quote, "stated_ref": tf.stated_ref, "found_in_ref": tf.found_in_ref},
                      summary=f"Talmud quote misattributed to {tf.stated_ref}, found in {tf.found_in_ref}")

    assert len(recorded) == 1
    kind, intent, detail = recorded[0]
    assert kind == "citation_mismatch"
    assert intent == "qa"
    assert detail["stated_ref"] == "Shevuot.33b"
    assert detail["found_in_ref"] == "Shevuot.31b"
