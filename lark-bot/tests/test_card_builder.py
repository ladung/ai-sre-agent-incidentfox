from __future__ import annotations

from card_builder import build_status_card, build_streaming_card, build_final_card, build_error_card


def test_status_card_has_header_and_body():
    card = build_status_card(prompt="why is checkout slow?")
    assert card["schema"] == "2.0"
    assert card["header"]["title"]["content"] == "IncidentFox Investigation"
    body_texts = [el["text"]["content"] for el in card["body"]["elements"] if el["tag"] == "div"]
    assert any("Investigating" in t for t in body_texts)
    assert any("why is checkout slow?" in t for t in body_texts)


def test_streaming_card_shows_partial_result():
    card = build_streaming_card(prompt="p", partial_text="Looking at logs…")
    body_texts = [el["text"]["content"] for el in card["body"]["elements"] if el["tag"] == "div"]
    assert any("Looking at logs" in t for t in body_texts)


def test_streaming_card_chunks_long_partial():
    long_text = "x" * 9000
    card = build_streaming_card(prompt="p", partial_text=long_text)
    div_count = sum(1 for el in card["body"]["elements"] if el["tag"] == "div")
    # 1 status div + at least 3 chunks for 9000 chars
    assert div_count >= 4


def test_final_card_success_styling():
    card = build_final_card(prompt="p", result_text="Found it: pod OOM.", success=True)
    assert card["header"]["template"] == "green"


def test_final_card_failure_styling():
    card = build_final_card(prompt="p", result_text="error", success=False)
    assert card["header"]["template"] == "red"


def test_error_card_includes_error_text():
    card = build_error_card(prompt="p", error="orchestrator unreachable")
    body_texts = [el["text"]["content"] for el in card["body"]["elements"] if el["tag"] == "div"]
    assert any("orchestrator unreachable" in t for t in body_texts)
    assert card["header"]["template"] == "red"
