from __future__ import annotations

from embed_builder import (
    COLOR_BLUE,
    COLOR_GREEN,
    COLOR_RED,
    build_status_embed,
    build_streaming_embed,
    build_final_embed,
    build_error_embed,
    embeds_for_long_result,
)


def test_status_embed_has_blue_color_and_prompt():
    e = build_status_embed(prompt="why is checkout slow?")
    assert e["color"] == COLOR_BLUE
    assert e["title"] == "IncidentFox Investigation"
    assert "Investigating" in e["description"]
    assert "why is checkout slow?" in e["description"]


def test_streaming_embed_shows_partial_text():
    e = build_streaming_embed(prompt="p", partial_text="Looking at logs…")
    assert e["color"] == COLOR_BLUE
    assert "Looking at logs" in e["description"]


def test_streaming_embed_truncates_overlong_partial():
    """The streaming embed should NOT exceed the 4096 hard limit. Partial overflow is dropped
    in favor of an end marker indicating more is coming. The final embed handles fan-out."""
    long_text = "x" * 9000
    e = build_streaming_embed(prompt="p", partial_text=long_text)
    assert len(e["description"]) <= 4096


def test_final_embed_success_styling():
    e = build_final_embed(prompt="p", result_text="Found it: pod OOM.", success=True)
    assert e["color"] == COLOR_GREEN
    assert e["title"] == "Investigation Complete"


def test_final_embed_failure_styling():
    e = build_final_embed(prompt="p", result_text="error", success=False)
    assert e["color"] == COLOR_RED
    assert e["title"] == "Investigation Failed"


def test_error_embed_includes_error_text():
    e = build_error_embed(prompt="p", error="orchestrator unreachable")
    assert e["color"] == COLOR_RED
    assert "orchestrator unreachable" in e["description"]


def test_embeds_for_long_result_returns_one_per_chunk():
    long_result = "p1\n\n" + ("a" * 5000) + "\n\np3"
    embeds = embeds_for_long_result(prompt="q", result_text=long_result, success=True)
    # Long result should fan into ≥2 embeds
    assert len(embeds) >= 2
    # First embed is the "primary" (header). Continuation embeds carry "(continued)" footer.
    assert embeds[0].get("footer") is None or "continued" not in embeds[0]["footer"].get("text", "").lower()
    for e in embeds[1:]:
        assert "continued" in e["footer"]["text"].lower()
    # All embeds within 4096
    for e in embeds:
        assert len(e["description"]) <= 4096
