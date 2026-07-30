"""Rights classification for corpus text — one place that decides what may be reproduced.

Sefaria does NOT license its corpus under one licence. `Sefaria-Export/LICENSE.md` says it plainly:
"Each text is licensed separately... You can find the license for each text in their JSON versions
under the `license` field." The value is scoped to (title, language, versionTitle) — NOT to the
work, the author, or our `work_id` tiers, none of which line up with rights boundaries:

  * Talmud Bavli's DEFAULT version (William Davidson Edition) is CC-BY-NC — in Hebrew AND English —
    while the underlying Aramaic is public domain.
  * "Peninei Halakhah" is CC-BY-NC in Hebrew and CC0 in English (Sefaria Community Translation).
  * "Steinsaltz" is not one licence: the WDT translation is CC-BY-NC, but `Steinsaltz on Mishneh
    Torah` is "Copyright: Steinsaltz Center" — no Creative Commons grant at all.

Verified live against sefaria.org's API on 2026-07-17.

The rule that matters commercially: **NonCommercial attaches to the USE, not to who is using it.**
Creative Commons' own FAQ: "charging for access may not be permitted with NC-licensed material."
Reproducing CC-BY-NC text to subscribers as part of what they pay for is a violation. Retrieving it
as invisible LLM context is a genuinely unsettled legal question (active 2025 litigation, no
rulings) — but this product also DISPLAYS source text verbatim, and that part is not unsettled.

None of this is legal advice; it encodes the licence terms so the product can act on them.
"""

from __future__ import annotations

# Sefaria's `license` strings, normalised (lowercased, stripped).
_PUBLIC_DOMAIN = {"public domain", "public domain mark", "pd"}
_CC0 = {"cc0", "cc0 1.0", "cc zero"}
_CC_BY = {"cc-by", "cc by", "cc-by 4.0", "cc-by-sa", "cc by-sa", "cc-by-sa 4.0"}
_CC_NC_PREFIXES = ("cc-by-nc", "cc by-nc", "cc-nc")

# Attribution is required by these; CC0/PD do not require it (crediting anyway is good manners).
_REQUIRES_ATTRIBUTION = _CC_BY | {p for p in _CC_NC_PREFIXES}


def normalize(license_str: str | None) -> str:
    return (license_str or "").strip().lower()


def is_unknown(license_str: str | None) -> bool:
    """No licence recorded, or Sefaria itself recorded 'unknown'.

    A large share of real Sefaria versions fall here — Sefaria has not verified their copyright
    status. Unknown is NOT permission: it is treated exactly like all-rights-reserved.
    """
    lic = normalize(license_str)
    return lic in {"", "unknown", "none", "null"}


def is_noncommercial(license_str: str | None) -> bool:
    """CC-BY-NC and friends — free to use, but not in something you charge for."""
    return normalize(license_str).startswith(_CC_NC_PREFIXES)


def is_copyrighted(license_str: str | None) -> bool:
    """A bare copyright claim, e.g. 'Copyright: Steinsaltz Center'. No grant at all."""
    return normalize(license_str).startswith("copyright")


def allows_commercial_use(license_str: str | None) -> bool:
    """May this text be reproduced in something we charge money for?

    True only for licences that positively grant it: Public Domain, CC0, CC-BY, CC-BY-SA.
    Everything else — NC, explicit copyright, unknown, unrecognised — is False. Fail closed: the
    cost of wrongly excluding a source is a thinner answer; the cost of wrongly including one is
    an infringement claim.
    """
    lic = normalize(license_str)
    if is_unknown(lic) or is_noncommercial(lic) or is_copyrighted(lic):
        return False
    return lic in _PUBLIC_DOMAIN or lic in _CC0 or lic in _CC_BY


def requires_attribution(license_str: str | None) -> bool:
    """CC-BY / CC-BY-SA / CC-BY-NC require credit. Generic 'Sefaria' is not enough — CC asks for
    TASL (Title, Author, Source, Licence)."""
    lic = normalize(license_str)
    return lic in _CC_BY or is_noncommercial(lic)


def attribution_line(*, ref: str, version_title: str, license_str: str, deep_link: str = "") -> str:
    """A TASL-shaped credit for one source: what it is, which edition, where, under what licence."""
    parts = [p for p in (ref, version_title) if p]
    line = " — ".join(parts) if parts else (ref or "")
    if deep_link:
        line += f" ({deep_link})"
    if license_str:
        line += f" [{license_str}]"
    return line


def is_share_alike(license_str: str | None) -> bool:
    """CC-BY-SA — the one licence here that constrains what may be done with a document CONTAINING
    the text, not just with the text. 87 sources in the shipped corpus."""
    return normalize(license_str).startswith(("cc-by-sa", "cc by-sa"))


_BY_DEED = "https://creativecommons.org/licenses/by/4.0/"
_BY_SA_DEED = "https://creativecommons.org/licenses/by-sa/4.0/"


def document_license_notice(sources: list[tuple[str, str]], lang: str = "he") -> str:
    """The licence footer for a document that REPRODUCES corpus text — a source sheet, a lesson.

    `sources` is (ref, licence) per reproduced source. Returns "" when nothing in the document
    carries an obligation, which is the common case: Public Domain and CC0 are 6,543 of the 6,630
    sources in the corpus and neither asks for anything, so most sheets get no footer at all.

    Why a footer at all, when every CC-BY source already carries its own credit line: attribution
    answers "who wrote this passage", and share-alike answers "what may the person holding this FILE
    do with it". A teacher who downloads a source sheet, edits it and hands it on has taken on an
    obligation that is nowhere on the page unless it is written there. Naming the CC-BY-SA refs
    explicitly is the part that makes it actionable — "some of this is share-alike" tells a reader
    they have a problem without telling them where it is.

    A deliberate line is drawn here, and it is the one point in this file a lawyer should look at.
    A source sheet that reproduces passages intact alongside our own material is a COLLECTION under
    CC 4.0, not Adapted Material, so share-alike attaches to the passages and does not swallow the
    lesson written around them. Had we taken the other reading, every lesson touching one of those 87
    sources would have to ship under CC-BY-SA — including the teacher's own work. The notice states
    the obligation on the parts, which is true under either reading; what it does not do is license
    the whole document away on the strength of the stricter one.
    """
    he = (lang or "he").startswith("he")
    sa = [ref for ref, lic in sources if ref and is_share_alike(lic)]
    by = [ref for ref, lic in sources
          if ref and requires_attribution(lic) and not is_share_alike(lic)]
    if not sa and not by:
        return ""

    lines = ["---", "**רישוי המסמך**" if he else "**Licensing of this document**", ""]
    if by:
        # Hebrew does not take a bare numeral before a plural the way English does — "משעתק 1
        # מקורות" reads as a bug in the document, which is not the impression a licence notice
        # should make.
        how_many = "מקור אחד" if len(by) == 1 else f"{len(by)} מקורות"
        lines.append(
            f"מסמך זה משעתק {how_many} ברישיון CC BY 4.0. ההעתקה וההפצה מותרות — "
            f"בתנאי ששורת הייחוס שלצד כל מקור נשמרת. שורת הייחוס היא תנאי הרישיון, לא נימוס; "
            f"הסרתה מפקיעה את ההיתר. {_BY_DEED}" if he else
            f"This document reproduces {len(by)} source(s) under CC BY 4.0. You may copy and "
            f"redistribute them provided the credit line beside each is kept. That credit is a "
            f"condition of the licence, not a courtesy: removing it ends the permission. {_BY_DEED}")
        lines.append("")
    if sa:
        named = ", ".join(sa[:10])
        extra = len(sa) - 10
        more = "" if extra <= 0 else (f" (ועוד {extra})" if he else f" (and {extra} more)")
        lines.append(
            f"המקורות הבאים הם ברישיון **CC BY-SA 4.0**: {named}{more}. מלבד הייחוס, רישיון זה "
            f"דורש **שיתוף זהה**: כל עיבוד שלהם — תרגום, קיצור, ניסוח מחדש — חייב להיות מופץ תחת "
            f"אותו רישיון. שעתוק הקטעים כפי שהם, כפי שנעשה כאן, אינו מחייב את שאר המסמך. "
            f"{_BY_SA_DEED}" if he else
            f"The following sources are under **CC BY-SA 4.0**: {named}{more}. Beyond attribution "
            f"this licence requires **share-alike**: any adaptation of them — translation, "
            f"abridgement, rewording — must be distributed under the same licence. Reproducing the "
            f"passages unchanged, as here, does not bind the rest of the document. {_BY_SA_DEED}")
        lines.append("")
    lines.append("מקורות שאינם מופיעים כאן הם נחלת הכלל או CC0 ואינם מחייבים דבר."
                 if he else
                 "Sources not listed here are Public Domain or CC0 and carry no obligation.")
    return "\n".join(lines)


def commercial_filter_values(available: list[str]) -> list[str]:
    """The subset of licence values present in the corpus that a PAID tier may reproduce.

    Returned as a list so it can be handed straight to a store filter (Qdrant matches a keyword
    field against a set of allowed values).
    """
    return [lic for lic in available if allows_commercial_use(lic)]
