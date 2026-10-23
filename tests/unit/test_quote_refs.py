"""Quote references: the model writes {{S#: start … end}}, the code pastes the verbatim span."""

from chavruta.generation.grounded import expand_quote_refs

SRC = {
    1: "מתני׳ שנים אוחזין בטלית זה אומר אני מצאתיה וזה אומר אני מצאתיה זה ישבע שאין לו בה פחות מחציה ויחלוקו",
    2: "וכ\"ש. דהוי נ\"ט בר נ\"ט ש\"ך ולכאורה דמיירי אחר מעל\"ע מחלב",
    3: "אֵין זָקוּק לָהּ וּמוּתָּר לְהִשְׁתַּמֵּשׁ לְאוּרָהּ",
}


def test_span_between_anchors_is_pasted_verbatim():
    out, st = expand_quote_refs("המשנה: {{S1: שנים אוחזין … פחות מחציה}} כך.", SRC)
    assert '"שנים אוחזין בטלית זה אומר אני מצאתיה וזה אומר אני מצאתיה זה ישבע שאין לו בה פחות מחציה" [S1]' in out
    assert st == {"ok": 1, "moved": 0, "unmatched": 0}


def test_short_phrase_without_end_anchor():
    out, _ = expand_quote_refs("{{S1: ישבע שאין לו בה}}", SRC)
    assert out == '"ישבע שאין לו בה" [S1]'


def test_abbreviations_and_niqqud_match_but_original_text_is_kept():
    out, st = expand_quote_refs('{{S2: דהוי נ"ט בר נ"ט}} ו-{{S3: אין זקוק לה}}', SRC)
    assert 'דהוי נ"ט בר נ"ט' in out
    assert '"אֵין זָקוּק לָהּ" [S3]' in out
    assert st["ok"] == 2


def test_wrong_marker_is_moved_to_the_source_that_has_it():
    out, st = expand_quote_refs("{{S3: שנים אוחזין בטלית}}", SRC)
    assert out == '"שנים אוחזין בטלית" [S1]'
    assert st["moved"] == 1


def test_unfindable_quote_loses_quotes_and_marker():
    out, st = expand_quote_refs("כתוב {{S1: משפט שלא קיים בשום מקור}} כאן", SRC)
    assert out == "כתוב משפט שלא קיים בשום מקור כאן"
    assert '"' not in out and "[S" not in out
    assert st["unmatched"] == 1


def test_unknown_marker_number_is_not_trusted():
    out, st = expand_quote_refs("{{S9: אין זקוק לה}}", SRC)
    assert out == '"אֵין זָקוּק לָהּ" [S3]'
    assert st["moved"] == 1


def test_long_span_is_capped():
    big = {1: " ".join(f"מילה{i}" for i in range(400))}
    out, _ = expand_quote_refs("{{S1: מילה0 … מילה399}}", big)
    assert out.endswith('…" [S1]') or "…" in out
    assert len(out) < 700


def test_text_without_refs_is_untouched():
    t = 'רגיל "ציטוט" [S1] בלי הפניות'
    assert expand_quote_refs(t, SRC) == (t, {"ok": 0, "moved": 0, "unmatched": 0})
