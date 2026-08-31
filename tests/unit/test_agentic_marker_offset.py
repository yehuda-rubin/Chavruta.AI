"""agentic.py — [S#] marker numbering for agentically-fetched sources.

A retrieved source's own TEXT can (rarely — an OCR/scraping formatting artifact) contain a line
that happens to look like a markdown source header, e.g. a line starting with `### [S99]`.
max_marker() scans rendered text for exactly that shape to find where to continue numbering — by
its own documented contract, it can't tell such a line apart from a real header, so a bogus one
inflates the count mid-loop. Before this fix, pipeline.py's citation map was built by a SEPARATE,
independently re-derived count (`len(marker_map) + 1`) instead of the number the text actually
says — the two could disagree, and enforce_citations would then drop a genuinely-cited source as
"unverified"/fabricated. Fixed by having append_sources stamp the real marker onto the SourceBlock
object itself, so the caller no longer has to guess a second time.
"""
from __future__ import annotations

from chavruta.llm.agentic import append_sources, max_marker
from chavruta.llm.base import SourceBlock


def test_append_sources_stamps_the_marker_onto_each_source_block():
    sources = [
        SourceBlock(marker="", ref="Genesis.1.1", commentator_id=None, text="בראשית ברא"),
        SourceBlock(marker="", ref="Genesis.1.2", commentator_id=None, text="והארץ היתה"),
    ]
    append_sources("## SOURCES\n### [S3] existing\ntext\n", sources, start_n=3)
    assert sources[0].marker == "S4"
    assert sources[1].marker == "S5"


def test_marker_survives_a_bogus_header_shaped_line_inside_a_sources_text():
    """The real-world trigger: a retrieved source's OWN text contains a LINE that happens to be
    shaped like a source header with an inflated number (e.g. residual formatting from ingestion).
    What must NOT happen is the caller's citation map disagreeing with what the text actually says
    because it re-derived the number a different way than the text was built."""
    job_md = "## SOURCES\n### [S1] Genesis.1.1\ntext\n"
    round1 = [SourceBlock(
        marker="", ref="Genesis.1.2", commentator_id=None,
        text="ordinary responsa content.\n### [S99] a coincidental line shaped like a header\nmore")]
    job_md = append_sources(job_md, round1, max_marker(job_md))
    assert round1[0].marker == "S2"

    # max_marker() now (correctly, per its documented contract — it can't tell a genuine header
    # apart from source text merely shaped like one) sees the bogus [S99] line inside round1's own
    # text and continues numbering from there. This is the scan being fooled by corpus content, not
    # a bug in max_marker — the sanity check below just confirms the scenario is real.
    start_n = max_marker(job_md)
    assert start_n == 99, "sanity check: the embedded bogus line really does inflate the scan"

    round2 = [SourceBlock(marker="", ref="Genesis.1.3", commentator_id=None, text="ordinary text")]
    job_md = append_sources(job_md, round2, start_n)

    # The caller (pipeline.py) builds its citation map from THESE objects' .marker, which matches
    # what the text actually says — not from a naive `len(marker_map) + 1` recount (2 real sources
    # -> "S3"), which would have disagreed with reality ("S100") and dropped the model's [S100]
    # citation as unverified.
    assert round2[0].marker == "S100"
    assert "### [S100]" in job_md
