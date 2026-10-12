"""Streaming generator and sliding-window citation marker filter for Chavruta.AI.

Combines server-side marker suppression (preventing raw `[S#]` leaks) with
structured SSE events so the UI receives clean, flowing text while simultaneously
getting real-time citation chips and source highlights.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

from chavruta.corpus.refs import hebrew_display_ref
from chavruta.retrieval.base import RankedHit

_MARKER_RE = re.compile(r"^\[S(\d+)\]")


def stream_with_marker_transformation(
    raw_token_stream: Iterator[str],
    hits: list[RankedHit],
) -> Iterator[str]:
    """Sliding-window buffer stream transformer (Hybrid Solutions 1 + 2).

    Yields formatted Server-Sent Events (SSE):
      - `event: token\ndata: {"text": "..."}\n\n`
      - `event: citation\ndata: {"marker": "S1", "ref": "...", "ref_he": "..."}\n\n`
    """
    marker_map: dict[str, RankedHit] = {f"S{i}": h for i, h in enumerate(hits, start=1)}
    buf = ""

    for chunk in raw_token_stream:
        buf += chunk
        while True:
            open_bracket = buf.find("[")
            if open_bracket == -1:
                # No bracket found, emit the full buffer as text tokens
                if buf:
                    yield f"event: token\ndata: {json.dumps({'text': buf}, ensure_ascii=False)}\n\n"
                    buf = ""
                break

            # Emit any text preceding the '['
            if open_bracket > 0:
                pre_text = buf[:open_bracket]
                yield f"event: token\ndata: {json.dumps({'text': pre_text}, ensure_ascii=False)}\n\n"
                buf = buf[open_bracket:]

            # Now buf starts with '['
            close_bracket = buf.find("]")
            if close_bracket == -1:
                # Still waiting for ']'
                # If buffer is too long without ']', it's regular text, not a marker
                if len(buf) > 15:
                    yield f"event: token\ndata: {json.dumps({'text': buf[0]}, ensure_ascii=False)}\n\n"
                    buf = buf[1:]
                else:
                    # Wait for next chunk to complete the potential marker
                    break
            else:
                bracket_text = buf[:close_bracket + 1]
                match = _MARKER_RE.match(bracket_text)
                if match:
                    idx = match.group(1)
                    marker_key = f"S{idx}"
                    hit = marker_map.get(marker_key)
                    ref_str = str(getattr(hit, "ref", "") or "")
                    payload: dict[str, Any] = {
                        "marker": marker_key,
                        "index": int(idx),
                        "ref": ref_str,
                        "ref_he": str(hebrew_display_ref(ref_str) or ref_str) if hit else "",
                        "text_he": str(getattr(hit, "text_he", "") or "") if hit else "",
                        "commentator": str(getattr(hit, "commentator_id", "") or "") if hit else "",
                        "deep_link": str(getattr(hit, "deep_link", "") or "") if hit else "",
                    }
                    # 1. Structured citation event for real-time sidebar & source chips
                    yield f"event: citation\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                    # 2. Clean numeric footnote token e.g. [1] replacing raw [S1]
                    yield f"event: token\ndata: {json.dumps({'text': f'[{idx}]'}, ensure_ascii=False)}\n\n"
                else:
                    # Normal bracketed text (not a source marker)
                    yield f"event: token\ndata: {json.dumps({'text': bracket_text}, ensure_ascii=False)}\n\n"
                buf = buf[close_bracket + 1:]

    # Flush remaining buffer at stream end
    if buf:
        yield f"event: token\ndata: {json.dumps({'text': buf}, ensure_ascii=False)}\n\n"
