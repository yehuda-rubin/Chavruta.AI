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


def commercial_filter_values(available: list[str]) -> list[str]:
    """The subset of licence values present in the corpus that a PAID tier may reproduce.

    Returned as a list so it can be handed straight to a store filter (Qdrant matches a keyword
    field against a set of allowed values).
    """
    return [lic for lic in available if allows_commercial_use(lic)]
