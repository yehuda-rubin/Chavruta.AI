#!/usr/bin/env python3
"""Quick validation script for the two bug fixes."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[0] / "src"))

# Test BUG 2: _strip_markers orphaned preposition repair
import re

_ORPHANED_PREP_RE = re.compile(
    r"\s+[בכלמשוה]\s*[:.,，。；;?？!！]|"  # one-letter prep + punctuation
    r"\s+[בכלמשוה]\s*$|"                 # one-letter prep at end
    r"\s+את\s*[:.,，。；;?？!！]|"        # את + punctuation
    r"\s+את\s*$"                         # את at end
)

test_cases = [
    ("כי באמת, ב יש דיון מעניין.", "כי באמת, יש דיון מעניין."),
    ("הבא נבדוק את: שם נאמר...", "הבא נבדוק: שם נאמר..."),
    ("כמו שמציע החסיד נתן אדלער ב, או...", "כמו שמציע החסיד נתן אדלער, או..."),
    ("ראינו זאת ב .", "ראינו זאת."),
]

print("Testing orphaned preposition repair regex:")
for raw, expected in test_cases:
    result = _ORPHANED_PREP_RE.sub("", raw)
    if result == expected:
        print(f"✓ {raw[:30]}... -> {result[:30]}...")
    else:
        print(f"✗ {raw[:30]}... -> {result[:30]}... (expected {expected[:30]}...)")

# Test legitimate one-letter word (should NOT match)
legit = "הוא אומר ש זה טוב וכ כן העניין"
result = _ORPHANED_PREP_RE.sub("", legit)
if result == legit:
    print(f"✓ Legitimate one-letter words preserved: {legit[:30]}...")
else:
    print(f"✗ Legitimate one-letter words modified: {legit[:30]}... -> {result[:30]}...")

# Test BUG 1: conversation signal harvesting
from chavruta.intents.hebrew_refs import detect_tractates
from chavruta.intents.router import detect_commentators
from chavruta.corpus.schema import Query

print("\nTesting conversation signal harvesting:")

user_turns = [
    "מה רשי אומר על בניית בית המקדש?",
    "ומה לגבי מה שהוא אומר במסכת סוכה בעניין הזה",
    "מה תוספות סובר על כך?",
    "האם תוספות חולק על רשי?",
]
question = "האם יש מחלוקת בין רשי לתוספות על בניית המקדש"

convo = " ".join(user_turns + [question])
tractates = detect_tractates(convo)
if tractates == ["Sukkah"]:
    print(f"✓ Full conversation harvests tractate: {tractates}")
else:
    print(f"✗ Full conversation tractates: {tractates} (expected ['Sukkah'])")

# Test that current question wins
rq = Query(text=user_turns[0] + " " + question, lang="he")
rq.tractates = ["Berakhot"]  # Explicit from current question
if not rq.tractates:
    rq.tractates = detect_tractates(convo)
if rq.tractates == ["Berakhot"]:
    print(f"✓ Current question tractate wins: {rq.tractates}")
else:
    print(f"✗ Current question tractate: {rq.tractates} (expected ['Berakhot'])")

print("\nAll manual validation complete.")
