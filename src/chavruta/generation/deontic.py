"""Internal deontic consistency of a generated answer — a coherence check on TEXT, never a ruling.

A halachic answer makes normative statements: something is אסור / מותר / חייב / פטור, usually
attributed to a source or a posek. The answer is internally incoherent — regardless of whether its
sources are real — if it says "הרמב\"ם אוסר" and then concludes that the same case is מותר with
nothing in between that explains the shift. That is a defect in the WRITING, and this module reports
it as exactly that: two spans of text that appear to say opposite things under one name.

**What this must never become.** It does not decide halacha, does not rank opinions, and does not
say which of the two spans is right — the constitution reserves that for a human posek
(Principle VIII), and docs/FORMAL_VERIFICATION.md §2 draws the same line: verifying that a text says
what it was said to say is not pesak, and must not be dressed up as pesak. That is why
`deontic_conflicts` returns a LIST of suspected pairs and never a boolean verdict on the answer:
"this answer is halachically wrong" is a judgement no string matcher is entitled to make.

Two properties of real halachic prose make the naive version of this check actively harmful, and
every rule below is built against them:

  • **A machloket is not a contradiction.** "בית שמאי אוסרים ובית הלל מתירים" is the correct
    description of reality — Principle VIII *requires* surfacing that disagreement rather than
    flattening it. Only ONE authority holding both sides is ever a candidate, and plural or
    anonymous voices ("יש אומרים", "הפוסקים", "האחרונים", "תוספות") are recognised here precisely
    so they can be excluded: they are a crowd, and a crowd is allowed to disagree with itself.
  • **A qualification is not a contradiction.** "אסור בשבת ומותר ביום חול", "לכתחילה אסור ובדיעבד
    מותר", "מדרבנן אסור ומדאורייתא מותר", "פטור בדיני אדם וחייב בדיני שמים" — this is the ordinary
    shape of the literature, not an error. Two statements pair only when their qualifier signatures
    are IDENTICAL; any marker present on one side and absent on the other silences the check.

So the checker is deliberately near-silent: every rule fails toward saying nothing. A checker that
fires on ordinary halachic prose is worse than no checker — it gets switched off within a day and
takes with it the one case it should have caught. Recall was traded away for that on purpose; the
"deliberately not caught" notes below are choices, not gaps waiting to be filled.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from chavruta.corpus.refs import COMMENTATOR_HE
from chavruta.intents.router import COMMENTATOR_ALIASES

_HEB = "א-ת"

# Same normalisation family as grounded.py's Hebrew handling: strip niqqud/cantillation, and fold
# the Hebrew gershayim/geresh onto ASCII so 'רמב״ם' and 'רמב"ם' are one name rather than two
# authorities that can never contradict each other.
_NIQQUD_RE = re.compile(r"[֑-ׇ]")
_QUOTE_MAP = str.maketrans({"״": '"', "”": '"', "“": '"', "„": '"', "׳": "'", "’": "'"})
_BRACKET_RE = re.compile(r"\[[^\[\]]*\]")

# Sentence is the unit of attribution. Splitting on ':' too was rejected: "הרמב\"ם כותב: אסור לטלטל"
# would put the name and the verdict in different units and force the weaker inherited attribution
# on a statement that is in fact explicit.
_SENTENCE_RE = re.compile(r"[^.!?\n•]+")

_WORD_RE = re.compile(rf"[{_HEB}\"']+")
_CASE_TOKEN_RE = re.compile(rf"[{_HEB}]{{3,}}")


def _alt(forms) -> str:
    """Alternation, longest first — 'בית שמאי' must win over any shorter alias inside it."""
    return "|".join(re.escape(f) for f in sorted(set(forms), key=len, reverse=True))


def _word_pattern(forms, prefixes: str) -> re.Pattern:
    """Whole-word Hebrew match allowing the stacked one-letter prefixes Hebrew glues on
    ('ולרש"י', 'שאסור'). Borrowed from router._alias_hit, which learned the hard way that a bare
    substring test fires 'רשי' inside 'מפרשים'; the same trap here would read 'איסור' as a verdict
    or invent an authority inside an unrelated word.

    `prefixes` is passed per call because the two callers need different sets: ש must be allowed on
    a verdict ('שאסור' — that it is forbidden) and must NOT be allowed on a name, where it would let
    'שרשי' match 'רשי'.
    """
    return re.compile(rf"(?<![{_HEB}])[{prefixes}]{{0,2}}({_alt(forms)})(?![{_HEB}])")


# ── Authorities ──────────────────────────────────────────────────────────────────────────────────
# Reuses the two Hebrew name tables the repo already maintains (router's COMMENTATOR_ALIASES for
# input parsing, refs' COMMENTATOR_HE for citation display) rather than starting a third one that
# would drift from both. Only poskim that answer *practical* questions — and so show up in halachic
# prose without appearing in either table — are added here.
_POSKIM: dict[str, tuple[str, ...]] = {
    # 'מרן' and 'המחבר' are left out on purpose: both are honorifics whose referent depends on the
    # writer (מרן is R. Yosef Karo in one community and R. Ovadia Yosef in another). Mapping an
    # ambiguous honorific to one id would MERGE two people — the one direction of error this module
    # must never make, since a merge manufactures a contradiction out of a machloket. Unresolved,
    # they fall to `_TITLED_NAME_RE` and silence their sentence instead.
    "shulchan_aruch": ("שולחן ערוך", 'שו"ע'),
    "rema": ('רמ"א', "רמא"),
    "mishnah_berurah": ("משנה ברורה", 'המשנ"ב'),
    "biur_halacha": ("ביאור הלכה",),
    "taz": ('ט"ז',),
    "shach": ('ש"ך',),
    "magen_avraham": ("מגן אברהם", 'מג"א'),
    "chayei_adam": ("חיי אדם",),
    "aruch_hashulchan": ("ערוך השולחן",),
    "kaf_hachaim": ("כף החיים",),
    "igrot_moshe": ("אגרות משה", "איגרות משה"),
    "chazon_ish": ("חזון איש",),
    "yalkut_yosef": ("ילקוט יוסף",),
    "gra": ('הגר"א', 'גר"א'),
    "raavad": ('ראב"ד',),
    "tur": ("הטור",),
    # The two houses are here for one reason: so the textbook machloket is read as TWO authorities
    # and never collapses into one. Leaving them unknown would be worse than useless — the sentence
    # would look unattributed and the verdicts could inherit a name from further up.
    "beit_shammai": ("בית שמאי",),
    "beit_hillel": ("בית הלל",),
}

# Voices that are plural or anonymous BY CONSTRUCTION. They are matched (so they break attribution
# inheritance and mark their sentence as spoken by someone) but never enter a conflict pair:
# "יש אומרים שמותר... ויש אומרים שאסור" is a machloket written correctly, and "הפוסקים נחלקו" is
# the literal word for one. Tosafot belongs here too — it is a school of many Ba'alei HaTosafot,
# and it genuinely holds both sides in different places.
_PLURAL_VOICES: tuple[str, ...] = (
    "יש אומרים", "יש מי שאומר", "יש מי שכתב", "יש מתירים", "יש אוסרים", "יש מחמירים", "יש מקילים",
    "יש חולקים", "המקילים", "המחמירים", "הפוסקים", "פוסקים", "האחרונים", "אחרונים",
    "הראשונים", "ראשונים", "המפרשים", "מפרשים", "חכמים", "רבנן", "רבותינו", "הגאונים",
    "תוספות", "התוספות", "בעלי התוספות", "הרבה פוסקים", "כמה פוסקים",
)
_PLURAL_IDS = {"tosafot"}   # drop from the imported tables; they are handled as plural voices


def _authority_aliases() -> dict[str, str]:
    """alias → authority id, over the three tables. Aliases are kept verbatim (no gershayim
    stripping) because one character is the whole difference between רמב"ם and רמב"ן."""
    out: dict[str, str] = {}
    for table in (COMMENTATOR_ALIASES, COMMENTATOR_HE, _POSKIM):
        for cid, aliases in table.items():
            if cid in _PLURAL_IDS:
                continue
            for alias in ((aliases,) if isinstance(aliases, str) else aliases):
                alias = (alias or "").strip().translate(_QUOTE_MAP)
                # English aliases ('rashi') are dropped: this reads Hebrew answers, and a bare Latin
                # token is far likelier to be part of a ref ('Rashi_on_Genesis.1.1.1') than a claim.
                if alias and re.search(f"[{_HEB}]", alias):
                    out.setdefault(alias, cid)
    return out


_ALIAS_TO_ID = _authority_aliases()
_AUTHORITY_RE = _word_pattern(_ALIAS_TO_ID, "והבכלמ")
_PLURAL_RE = _word_pattern(_PLURAL_VOICES, "והבכלמ")
# A named person the tables do not know ('רבי עקיבא', 'הרב משה פיינשטיין'). Their identity does not
# have to resolve — what matters is that the sentence HAS a speaker, so its verdict is not silently
# credited to whoever was named two paragraphs earlier.
_TITLED_NAME_RE = re.compile(rf"(?<![{_HEB}])(?:רבי|רבן|הרב|רב|מרן|הגאון)\s+([{_HEB}]{{2,}})")

# Attribution cues without any recognisable name — "כתב שאסור", "לדעתו מותר". The speaker is someone
# this module cannot identify, so the statement is dropped and inheritance is broken. Without this,
# an unrecognised posek's ruling would be attributed to the last name that happened to be matched.
_ATTRIBUTION_CUE_RE = _word_pattern(
    ("כתב", "כתבו", "פסק", "פסקו", "סובר", "סוברים", "דעת", "דעתו", "שיטת", "שיטתו",
     "לדעת", "לשיטת", "בשם", "הביא", "מביא", "נקט", "הכריע", "מרן"),
    "והבכלמש",
)


# ── Verdicts ─────────────────────────────────────────────────────────────────────────────────────
# Only adjectival/verbal forms. The NOUNS איסור/היתר/חיוב are excluded on purpose: "דיני איסור
# והיתר" is the NAME of a subject, and "יש בזה צד איסור וצד היתר" is a description of a discussion —
# reading either as two opposite rulings on one case is the single easiest way to fire on prose that
# is doing nothing wrong.
_VERDICT_FORMS: dict[tuple[str, str], tuple[str, ...]] = {
    ("permission", "forbid"): ("אסור", "אסורה", "אסורים", "אסורות", "אוסר", "אוסרת", "אוסרים",
                               "לאסור", "נאסר"),
    ("permission", "permit"): ("מותר", "מותרת", "מותרים", "מותרות", "מתיר", "מתירה", "מתירים",
                               "להתיר", "הותר", "שרי"),
    ("liability", "obligate"): ("חייב", "חייבת", "חייבים", "חייבות", "מחייב", "מחייבת",
                                "מחייבים", "מחויב", "לחייב"),
    ("liability", "exempt"): ("פטור", "פטורה", "פטורים", "פטורות", "פוטר", "פוטרת", "פוטרים",
                              "לפטור"),
}
# Which polarity contradicts which. Deliberately only within an axis: "פטור אבל אסור" is a famous
# phrase and a coherent one — exemption from liability and prohibition are different questions.
_OPPOSITE = {"forbid": "permit", "permit": "forbid", "obligate": "exempt", "exempt": "obligate"}

_VERDICT_RES = {key: _word_pattern(forms, "והשכלבמ") for key, forms in _VERDICT_FORMS.items()}

# A negated verdict is dropped rather than flipped. "אין לומר שאסור" is not a heter, and deciding
# what "אינו אסור" licenses is interpretation — which is the thing this module refuses to do.
_NEGATION_RE = _word_pattern(
    ("לא", "לאו", "אין", "אינו", "אינה", "אינם", "אינן", "בלתי", "אי"), "וש")
_NEGATION_WINDOW = 3   # words

# A hedged statement is not an assertion, so it cannot contradict one. Whole sentence is dropped.
_HEDGE_RE = _word_pattern(
    ("לכאורה", "אולי", "ייתכן", "יתכן", "נראה", "משמע", "כנראה", "שמא", "ספק", "מסופק",
     "צריך עיון", 'צ"ע', "יש להסתפק", "בערך", "כנראה"), "והשכלבמ")
_QUESTION_RE = _word_pattern(("האם", "וכי", "מדוע", "כיצד", "היכן", "מהו", "מהי"), "ו")


# ── Qualifiers ───────────────────────────────────────────────────────────────────────────────────
# The distinctions that make an apparent reversal the normal shape of a halachic sentence. Two
# statements pair only when these sets are EQUAL, so anything listed here is a silencer — which is
# why the list leans inclusive (a missing qualifier costs a false positive; an extra one costs at
# most a missed catch).
_QUALIFIERS: dict[str, tuple[str, ...]] = {
    "shabbat": ("בשבת", "שבת", "בשבתות", "השבת"),
    "yom_tov": ("ביום טוב", "יום טוב", 'יו"ט', "בחג", "חג", "במועד", "בחול המועד"),
    "weekday": ("בחול", "ביום חול", "בימות החול", "בימי החול"),
    "lechatchila": ("לכתחילה", "לכתחלה"),
    "bedieved": ("בדיעבד", "דיעבד"),
    "deoraita": ("מדאורייתא", "דאורייתא", "מן התורה", "מדין תורה", "מדאוריתא"),
    "derabanan": ("מדרבנן", "דרבנן", "מדברי סופרים", "מדבריהם"),
    "duress": ("בשעת הדחק", "שעת הדחק", "בהפסד מרובה", "הפסד מרובה", "במקום צורך", "לצורך גדול",
               "לצורך", "לצורך גופו", "לצורך מקומו", "בשעת הצורך", "במקום מצוה", "לצורך מצוה",
               "בדוחק", "במקום חולי", "לחולה", "לצורך מצווה", "במקום מצווה"),
    "forum": ("בדיני שמים", "בידי שמים", "בדיני אדם", 'בב"ד', "בבית דין"),
    "minhag": ("מנהג", "המנהג", "נהגו", "נוהגים", "למנהג", "כמנהג"),
    "edah": ("לספרדים", "לאשכנזים", "לבני ספרד", "לבני אשכנז", "לתימנים"),
    "place": ("בארץ ישראל", "בחוץ לארץ", 'בחו"ל', "בירושלים", "במקדש"),
    "person": ("לאישה", "לאשה", "לנשים", "לאיש", "לגברים", "לקטן", "לקטנים", "לכהן", "לזקן"),
    "domain": ("ברשות הרבים", "ברשות היחיד", "בפרהסיא", "בצנעה", "בכרמלית"),
    "conditional": ("אם", "אילו", "אלמלא", "כאשר", "כשהוא", "במקרה", "בתנאי", "כל עוד", "ובלבד"),
}
_QUALIFIER_RES = {name: _word_pattern(forms, "והבכלמש") for name, forms in _QUALIFIERS.items()}

# Markers that a shift between two statements is EXPLAINED. Searched across the whole region from
# the first statement's sentence to the second's, so a contrast word anywhere in or between them
# silences the pair. These are the words a writer actually uses when moving from one view to another
# ("אך", "אמנם", "מאידך"), when reporting a dispute ("נחלקו", "מחלוקת"), when separating theory from
# practice ("למעשה", "המנהג"), or when drawing a distinction ("במה דברים אמורים", "ודוקא").
#
# 'לדעת' / 'שיטת' / 'דעת' are deliberately NOT here even though they mark a change of speaker: they
# are the ordinary way to attribute a view at all ("לדעת הרמב\"ם אסור"), and blocking on them would
# silence nearly every explicitly-attributed statement in the corpus of things this could catch.
_SHIFT_RE = _word_pattern(
    ("אך", "אבל", "אמנם", "ברם", "אולם", "ואולם", "אלא", "ואילו", "לעומת", "מאידך", "מנגד",
     "מכל מקום", 'מ"מ', "אף על פי", 'אע"פ', "אעפי", "ואף", "חולק", "חולקים", "חלוקים", "נחלקו",
     "מחלוקת", "פליגי", "יש אומרים", "יש מי", "דעות", "שיטות", "למעשה", "המנהג", "נהגו",
     "נוהגים", "להקל", "להחמיר", "הכריע", "הכרעה", "דווקא", "דוקא", "במה דברים אמורים", 'בד"א',
     "יש לחלק", "לחלק", "מיהו", "ומיהו", "חזר בו", "במקום אחר", "לעומת זאת", "מצד שני",
     "אינו סותר", "אין סתירה"),
    "והבכלמש",
)

# Function words carry no information about WHICH case is being ruled on, so they are stripped
# before the two statements are compared. The list leans long on purpose: the shorter it is, the
# easier it is for two unrelated rulings to look like the same case on shared connectives alone.
_STOPWORDS = {
    "של", "את", "על", "אל", "כי", "זה", "זו", "כל", "מכל", "גם", "או", "עם", "מן", "מה", "יש",
    "אין", "הוא", "היא", "הם", "הן", "אשר", "כמו", "לפי", "אחר", "בין", "כן", "רק", "עוד", "לכן",
    "ולכן", "לפיכך", "ולפיכך", "לכך", "משום", "מפני", "כאן", "וכן", "אלא", "הרי", "זאת", "בזה",
    "כך", "וכך", "כלומר", "אפילו", "כדי", "אלה", "אלו", "שהוא", "שהיא", "ואם", "וכל", "הזה",
    "הזאת", "הללו", "אותו", "אותה", "אותם", "כפי", "ואף", "ולא", "וכו", "לגבי", "בנוגע", "בעניין",
    "בענין", "כתב", "כתבו", "כותב", "פסק", "פוסק", "סובר", "מביא", "לומר", "נאמר", "אמר", "ברור",
    "יותר", "פחות", "מאוד", "ממש", "כלל", "בכל", "בכך", "צריך", "ניתן", "אפשר", "משמע", "נראה",
    "לעיל", "להלן", "שם", "כאשר", "כדלהלן", "הדין", "ההלכה", "המקרה", "דבר", "דברים",
}

# Two statements must be talking about the same case, and "the same case" is judged only by the
# words the answer itself used — with the content words required to be IDENTICAL, not merely
# similar.
#
# A similarity threshold was tried first and is the wrong instrument. `_QUALIFIERS` can never be
# complete — halacha distinguishes on anything ("...לתינוק", "...בציבור", "...בזמן הזה") — and an
# unlisted distinction arrives as exactly one extra word, which any workable threshold lets through:
# with a three-word case, one added word still scores 0.75. Requiring equality turns that failure
# around, because it reads every word present on one side and absent on the other as a candidate
# distinction, and this module is not qualified to judge whether a distinction is a real one. The
# cost is real and accepted: a contradiction restated in different words is not caught.
_CASE_MIN_SHARED = 2


@dataclass(frozen=True)
class NormativeStatement:
    """One (authority, verdict) claim as written. `start`/`end` index the normalised text returned
    by `normalize` — identical to the input's offsets unless the answer carried niqqud."""

    authority: str            # id ('rambam') or '' when the speaker is plural/anonymous
    authority_written: str    # the name as it appears in the answer
    attribution: str          # 'explicit' (named in the same sentence) | 'inherited'
    axis: str                 # 'permission' (אסור/מותר) | 'liability' (חייב/פטור)
    polarity: str             # 'forbid' | 'permit' | 'obligate' | 'exempt'
    verdict: str              # the matched word
    qualifiers: frozenset[str]
    case: frozenset[str]      # content words describing what is being ruled on
    sentence: str
    start: int
    end: int
    plural: bool              # a crowd ("יש אומרים") — never eligible for a conflict


@dataclass(frozen=True)
class DeonticConflict:
    """Two spans that appear to say opposite things under one name. NOT a ruling that either span is
    wrong, and not a claim about the halacha — a report that the TEXT does not hold together."""

    authority: str
    axis: str
    first: NormativeStatement
    second: NormativeStatement
    shared_case: tuple[str, ...]
    attribution: str          # 'explicit' only if BOTH sides named the authority themselves


def normalize(text: str) -> str:
    """Niqqud out, gershayim folded to ASCII, [S#] citation scaffolding and markdown bold blanked.

    Every step except the niqqud strip is length-preserving, so offsets into the result line up with
    the original for the overwhelmingly common un-vocalised answer. `[S1]` becomes spaces rather
    than disappearing: it is prompt scaffolding, not prose, and letting 'S1' survive would put it in
    the case-token set where it could pass two unrelated rulings off as the same case.
    """
    t = _NIQQUD_RE.sub("", text or "").translate(_QUOTE_MAP)
    t = _BRACKET_RE.sub(lambda m: " " * len(m.group(0)), t)
    return t.replace("*", " ")


def _mask(s: str, spans) -> str:
    """Blank the given spans (1-for-1, offsets preserved) so they cannot become case tokens."""
    chars = list(s)
    for a, b in spans:
        for i in range(a, b):
            chars[i] = " "
    return "".join(chars)


def _negated(sentence: str, at: int) -> bool:
    window = _WORD_RE.findall(sentence[:at])[-_NEGATION_WINDOW:]
    return any(_NEGATION_RE.fullmatch(w) for w in window)


def _speaker(sentence: str) -> tuple[str, str, bool, list[tuple[int, int]], bool]:
    """(authority_id, name_as_written, is_plural, name_spans, blocked) for one sentence.

    `blocked` means the sentence has a speaker this module cannot pin down — two different named
    authorities, an unrecognised name, or an attribution cue with no name at all. Its verdicts are
    dropped AND inheritance is reset, because the alternative is crediting someone else's ruling to
    the last name that happened to match.
    """
    plural = list(_PLURAL_RE.finditer(sentence))
    named = list(_AUTHORITY_RE.finditer(sentence))
    titled = list(_TITLED_NAME_RE.finditer(sentence))
    spans = [m.span() for m in plural + named + titled]

    ids = {_ALIAS_TO_ID[m.group(1)] for m in named}
    # 'מרן השולחן ערוך' is one speaker written twice, not two — a titled match that OVERLAPS a
    # recognised name is the same person and must not make the sentence look ambiguous.
    named_spans = [m.span() for m in named]
    unknown_titled = [m for m in titled
                      if m.group(1) not in _ALIAS_TO_ID
                      and not any(m.start() < e and s < m.end() for s, e in named_spans)]

    if plural:
        return "", plural[0].group(0).strip(), True, spans, False
    if len(ids) > 1 or unknown_titled:
        return "", "", False, spans, True
    if ids:
        m = named[0]
        return next(iter(ids)), m.group(1), False, spans, False
    if _ATTRIBUTION_CUE_RE.search(sentence):
        return "", "", False, spans, True
    return "", "", False, spans, False


def normative_statements(text: str) -> list[NormativeStatement]:
    """Every (authority, verdict) claim this module is willing to stand behind, in order.

    Extraction is the conservative half of the check: a statement that is hedged, negated,
    interrogative, or whose speaker cannot be pinned down is not returned at all — silence beats a
    claim about who said what.
    """
    norm = normalize(text)
    out: list[NormativeStatement] = []
    inherited: str = ""       # last unambiguous single speaker, for sentences that name nobody

    for sm in _SENTENCE_RE.finditer(norm):
        sentence, base = sm.group(0), sm.start()
        authority, written, plural, name_spans, blocked = _speaker(sentence)

        if blocked:
            inherited = ""
            continue
        if plural:
            inherited = ""    # a crowd cannot lend its name to the next sentence
        elif authority:
            inherited = authority

        # A question restates the case rather than ruling on it; a hedge is not an assertion.
        # Both are dropped whole — the sentence's verdicts belong to neither side.
        if _HEDGE_RE.search(sentence) or _QUESTION_RE.search(sentence) \
                or norm[sm.end():sm.end() + 1] == "?":
            continue

        found = []
        for (axis, polarity), rx in _VERDICT_RES.items():
            for vm in rx.finditer(sentence):
                if not _negated(sentence, vm.start()):
                    found.append((axis, polarity, vm))
        if not found:
            continue

        speaker, attribution = authority, "explicit"
        if not speaker and not plural:
            speaker, attribution = inherited, "inherited"
            if not speaker:
                continue

        quals = frozenset(name for name, rx in _QUALIFIER_RES.items() if rx.search(sentence))
        case_src = _mask(sentence, name_spans + [m.span() for _, _, m in found])
        case = frozenset(t for t in _CASE_TOKEN_RE.findall(case_src) if t not in _STOPWORDS)

        for axis, polarity, vm in found:
            out.append(NormativeStatement(
                authority=speaker if not plural else "",
                authority_written=written,
                attribution=attribution,
                axis=axis,
                polarity=polarity,
                verdict=vm.group(0),
                qualifiers=quals,
                case=case,
                sentence=sentence.strip(),
                start=base,
                end=base + len(sentence),
                plural=plural,
            ))
    return out


def _same_case(a: NormativeStatement, b: NormativeStatement) -> tuple[str, ...] | None:
    """The described case, when both statements describe the SAME one — else None.

    The minimum count matters as much as the equality: two statements that share no content words
    at all are trivially "equal" on the empty set, and a bare "הרמב\"ם אוסר." / "הרמב\"ם מתיר."
    carries no evidence that the two are even about one subject.
    """
    if a.case != b.case or len(a.case) < _CASE_MIN_SHARED:
        return None
    return tuple(sorted(a.case))


def deontic_conflicts(text: str) -> list[DeonticConflict]:
    """Suspected internal contradictions in a generated answer — a list, possibly empty, NEVER a
    verdict on the answer as a whole and never a statement about the halacha.

    A pair is reported only when ALL of these hold; each condition exists to keep an ordinary,
    correctly-written halachic paragraph silent:

      • one and the same named authority on both sides (a machloket between two names, or any
        plural/anonymous voice, is excluded before this point);
      • opposite polarities on the SAME axis (אסור↔מותר, חייב↔פטור) — 'פטור אבל אסור' crosses axes
        and is coherent;
      • different sentences — 'בין אסור למותר' and 'איסור והיתר' put both poles in one breath while
        ruling on nothing;
      • identical qualifier signatures — any distinction on one side only is a legitimate one;
      • no marker of an explained shift anywhere in or between them;
      • the same case, described in the same content words — an extra word on either side is read
        as a distinction this module has no business evaluating.

    At most one pair per (authority, axis): this is a pointer to a place to look, and repeating the
    same defect across every combination of its statements would bury it.
    """
    norm = normalize(text)
    statements = [s for s in normative_statements(text) if s.authority and not s.plural]
    conflicts: list[DeonticConflict] = []
    reported: set[tuple[str, str]] = set()

    for i, first in enumerate(statements):
        for second in statements[i + 1:]:
            key = (first.authority, first.axis)
            if key in reported:
                continue
            if first.authority != second.authority or first.axis != second.axis:
                continue
            if _OPPOSITE[first.polarity] != second.polarity:
                continue
            if first.start == second.start:      # same sentence — see the docstring
                continue
            if first.qualifiers != second.qualifiers:
                continue
            if _SHIFT_RE.search(norm[first.start:second.end]):
                continue
            shared = _same_case(first, second)
            if shared is None:
                continue
            reported.add(key)
            conflicts.append(DeonticConflict(
                authority=first.authority,
                axis=first.axis,
                first=first,
                second=second,
                shared_case=shared,
                attribution=("explicit" if first.attribution == second.attribution == "explicit"
                             else "inherited"),
            ))
    return conflicts


__all__ = ["DeonticConflict", "NormativeStatement", "deontic_conflicts",
           "normalize", "normative_statements"]
