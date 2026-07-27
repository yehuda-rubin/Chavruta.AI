"""Work-level licence resolution — finding C of the 2026-07-27 legal review.

`license` and `version_title` are empty on all 2,403,599 points of the commercial corpus, so
`attribution_line()` rendered nothing while NOTICE.md promised that source sheets carry credit. That
matters for the 464 CC-BY and 87 CC-BY-SA sources, where attribution is a CONDITION of the licence:
fail it and the licence terminates, and the reproduction becomes ordinary infringement.

Licence belongs to the EDITION, not the chunk, so it is resolved per work at read time from a table
built out of the corpus build's own record of which edition it ingested.
"""

from __future__ import annotations

import pytest
from chavruta.corpus.refs import license_for_ref, work_title_for_ref


# ── Which work a ref belongs to ───────────────────────────────────────────────
# Every ref here is real, sampled from the live collection. They are the ones that defeat a
# "strip the trailing numbers" rule, which is why the title set decides instead of a regex.
@pytest.mark.parametrize("ref,title", [
    ("Genesis.1.1", "Genesis"),
    ("Beitzah.27.4", "Beitzah"),
    ("Rashi_on_I_Samuel.27.7.1", "Rashi on I Samuel"),
    ("Mishneh_Torah,_Forbidden_Foods.11.18", "Mishneh Torah, Forbidden Foods"),
    # 'Part 1' and 'Section 2' have identical shape and opposite answers — no rule over the string
    # can separate them; only the known titles can.
    ("Guide_for_the_Perplexed,_Part_1.1.1", "Guide for the Perplexed"),
    ("Chafetz_Chaim_on_Sifra,_Behar,_Section_2.2.8", "Chafetz Chaim on Sifra"),
    ("Shoel_uMeshiv_Mahadura_I.3.215.5", "Shoel uMeshiv Mahadura I"),      # name ends in a numeral
    ("Sha'ar_HaPesukim,_Parashat_Bereshit.71", "Sha'ar HaPesukim"),        # apostrophe
])
def test_work_title_is_matched_not_parsed(ref, title):
    assert work_title_for_ref(ref) == title


def test_a_longer_title_wins_over_a_shorter_one_that_prefixes_it():
    """Matching must be longest-first and land on a segment boundary, or 'Genesis' swallows
    'Genesis Rabbah' and every midrash gets attributed to the Chumash."""
    assert work_title_for_ref("Bereshit_Rabbah.1.1") != "Genesis"


# ── The licence itself ────────────────────────────────────────────────────────
def test_a_cc_by_sa_work_resolves_to_a_real_credit():
    """The case the whole change exists for: an attribution-required work in the Talmud tier."""
    lic, version = license_for_ref("Beitzah.27.4", "he")
    assert lic == "CC-BY-SA" and version


def test_the_language_decides_which_edition_is_credited():
    """Rights are per edition, so a work can be Public Domain in Hebrew and something else in
    English. Crediting the wrong side names an edition the reader is not being shown."""
    he = license_for_ref("Genesis.1.1", "he")[1]
    en = license_for_ref("Genesis.1.1", "en")[1]
    assert he and en and he != en


def test_an_unknown_work_degrades_to_empty_and_never_raises():
    """A missing licence must never break a query — it costs a credit line, not an answer."""
    assert license_for_ref("Totally_Made_Up_Work.1.1", "he") == ("", "")
    assert license_for_ref(None, "he") == ("", "")
    assert work_title_for_ref("") is None


# ── Through the retriever ─────────────────────────────────────────────────────
def test_the_payload_still_wins_when_a_fresh_ingest_wrote_one():
    """The table is a fallback, not an override: a collection that carries real per-chunk rights
    must keep reporting its own, or a future correct ingest would be silently overwritten."""
    from types import SimpleNamespace

    from chavruta.retrieval.hybrid import _to_hit

    h = _to_hit(SimpleNamespace(chunk_id="c", score=0.5, payload={
        "ref": "Beitzah.27.4", "text": "t", "lang": "he",
        "license": "CC0", "version_title": "Some Fresh Edition"}))
    assert h.license == "CC0" and h.version_title == "Some Fresh Edition"


def test_the_table_fills_in_when_the_payload_is_empty():
    from types import SimpleNamespace

    from chavruta.corpus import rights
    from chavruta.retrieval.hybrid import _to_hit

    h = _to_hit(SimpleNamespace(chunk_id="c", score=0.5,
                                payload={"ref": "Beitzah.27.4", "text": "t", "lang": "he"}))
    line = rights.attribution_line(ref=h.ref, version_title=h.version_title, license_str=h.license)
    assert "CC-BY-SA" in line and h.version_title in line


# ── Share-alike on the generated document ─────────────────────────────────────
# Attribution says who wrote a passage. Share-alike says what the person holding the FILE may do
# with it — an obligation that lands on a teacher who edits a downloaded sheet and hands it on, and
# that is invisible unless the document says so.

def test_a_sheet_of_public_domain_sources_gets_no_footer():
    """The common case. 6,543 of the corpus's 6,630 sources are PD or CC0 and ask for nothing;
    a licence footer on every sheet would be noise that teaches people to ignore it."""
    from chavruta.corpus import rights

    assert rights.document_license_notice([("Genesis.1.1", "Public Domain"),
                                           ("Rashi_on_Genesis.1.1.1", "CC0")]) == ""


def test_share_alike_sources_are_named_not_just_counted():
    """'Some of this is share-alike' tells a reader they have a problem without telling them where
    it is. The refs are what make the obligation actionable."""
    from chavruta.corpus import rights

    out = rights.document_license_notice([("Genesis.1.1", "Public Domain"),
                                          ("Beitzah.27.4", "CC-BY-SA")])
    assert "Beitzah.27.4" in out and "CC BY-SA 4.0" in out
    assert "creativecommons.org/licenses/by-sa/4.0" in out
    assert "Genesis.1.1" not in out             # PD sources are not listed as obligations


def test_attribution_only_sources_produce_a_footer_without_share_alike():
    from chavruta.corpus import rights

    out = rights.document_license_notice([("Some_Work.1.1", "CC-BY")])
    assert out and "BY-SA" not in out


def test_the_footer_follows_the_documents_language():
    from chavruta.corpus import rights

    he = rights.document_license_notice([("Beitzah.27.4", "CC-BY-SA")], "he")
    en = rights.document_license_notice([("Beitzah.27.4", "CC-BY-SA")], "en")
    assert "שיתוף זהה" in he and "share-alike" in en


def test_share_alike_is_recognised_in_the_forms_the_corpus_actually_stores():
    from chavruta.corpus import rights

    assert all(rights.is_share_alike(v) for v in ("CC-BY-SA", "cc by-sa 4.0", "CC-BY-SA 4.0"))
    assert not rights.is_share_alike("CC-BY")
    assert not rights.is_share_alike("")
