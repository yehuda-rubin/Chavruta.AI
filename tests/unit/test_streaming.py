import json
import pytest

from chavruta.llm.streaming import stream_with_marker_transformation
from chavruta.retrieval.base import RankedHit


def test_streaming_marker_transformation_clean_replacement():
    hit1 = RankedHit(chunk_id="c1", ref="Genesis.1.1", text="בראשית", score=0.95, text_he="בראשית ברא אלהים")
    hit2 = RankedHit(chunk_id="c2", ref="Genesis.1.2", text="והארץ", score=0.90, text_he="והארץ היתה תהו ובהו")

    raw_tokens = ["שלום ", "עולם ", "כמבואר ב-[", "S", "1", "] וב-[", "S", "2", "] ", "סוף."]
    events = list(stream_with_marker_transformation(raw_tokens, [hit1, hit2]))

    # Collect token texts
    token_texts = []
    citations = []
    for ev in events:
        lines = ev.strip().split("\n")
        ev_type = lines[0].replace("event: ", "").strip()
        data = json.loads(lines[1].replace("data: ", "").strip())
        if ev_type == "token":
            token_texts.append(data["text"])
        elif ev_type == "citation":
            citations.append(data)

    full_text = "".join(token_texts)
    assert "[S1]" not in full_text
    assert "[S2]" not in full_text
    assert "[1]" in full_text
    assert "[2]" in full_text
    assert "Genesis.1.1" in [c.get("ref") for c in citations]
    assert "Genesis.1.2" in [c.get("ref") for c in citations]


def test_streaming_regular_brackets_unaffected():
    hit = RankedHit(chunk_id="c1", ref="Berakhot.2a", text="מאימתי", score=0.9)

    raw_tokens = ["טקסט עם [סוגריים רגילים] שלא קשורים למקורות."]
    events = list(stream_with_marker_transformation(raw_tokens, [hit]))

    token_texts = []
    for ev in events:
        lines = ev.strip().split("\n")
        if lines[0] == "event: token":
            data = json.loads(lines[1].replace("data: ", ""))
            token_texts.append(data["text"])

    full_text = "".join(token_texts)
    assert "[סוגריים רגילים]" in full_text


def test_resolve_llm_mistral_override(monkeypatch):
    from unittest.mock import MagicMock
    import app.api as api_mod

    mock_pipeline = MagicMock()
    mock_pipeline.profile.llm_timeout_s = 45.0
    mock_pipeline.profile.llm_max_retries = 2
    monkeypatch.setattr(api_mod, "_get_pipeline", lambda: mock_pipeline)

    # Default local user without preset gets shared pipeline backend (None)
    res, llm, meter = api_mod._resolve_llm_for_request("local", "he", "qa", None)
    assert llm is None

    # Mistral is disabled; requests requesting mistral preset fall back to default shared backend (None)
    res, llm, meter = api_mod._resolve_llm_for_request("local", "he", "qa", None, preset="mistral-large-3")
    assert llm is None



def test_fallback_llm_streaming_behavior():
    from unittest.mock import MagicMock
    from chavruta.llm.fallback import FallbackLLM
    from chavruta.llm.base import GroundedPrompt

    primary = MagicMock()
    # Primary stream fails immediately
    primary.stream.side_effect = RuntimeError("Mistral 503 Overloaded")
    primary.model_id = "mistral-large-2512"

    secondary = MagicMock()
    secondary.stream.return_value = iter(["תשובה", " מנביוס"])
    secondary.model_id = "nebius-qwen"

    fallback = FallbackLLM(primary=primary, secondary=secondary)
    prompt = GroundedPrompt(system="sys", sources=[], question="user")

    tokens = list(fallback.stream(prompt, lang="he", max_tokens=100, temperature=0.2))
    assert tokens == ["תשובה", " מנביוס"]
    assert fallback.last_model_used == "nebius-qwen"


def test_fallback_llm_empty_stream_fails_over():
    from unittest.mock import MagicMock
    from chavruta.llm.fallback import FallbackLLM
    from chavruta.llm.base import GroundedPrompt

    primary = MagicMock()
    # Primary stream yields 0 tokens (empty output)
    primary.stream.return_value = iter([])
    primary.model_id = "mistral-large-2512"

    secondary = MagicMock()
    secondary.stream.return_value = iter(["תשובה", " לאחר ריק"])
    secondary.model_id = "nebius-qwen"

    fallback = FallbackLLM(primary=primary, secondary=secondary)
    prompt = GroundedPrompt(system="sys", sources=[], question="user")

    tokens = list(fallback.stream(prompt, lang="he", max_tokens=100, temperature=0.2))
    assert tokens == ["תשובה", " לאחר ריק"]
    assert fallback.last_model_used == "nebius-qwen"
