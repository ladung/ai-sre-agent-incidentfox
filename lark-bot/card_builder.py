from __future__ import annotations

from typing import Any

from markdown_utils import escape_lark_md, split_for_card_chunks, to_lark_md

CardDict = dict[str, Any]


def _div(content: str) -> dict[str, Any]:
    return {"tag": "div", "text": {"tag": "lark_md", "content": content}}


def _hr() -> dict[str, Any]:
    return {"tag": "hr"}


def _header(*, title: str, template: str) -> dict[str, Any]:
    return {
        "title": {"tag": "plain_text", "content": title},
        "template": template,  # blue | green | red | yellow | turquoise | grey
    }


def _shell(*, header: dict[str, Any], elements: list[dict[str, Any]]) -> CardDict:
    return {
        "schema": "2.0",
        "config": {"wide_screen_mode": True, "update_multi": True},
        "header": header,
        "body": {"elements": elements},
    }


def build_status_card(*, prompt: str) -> CardDict:
    safe = escape_lark_md(prompt)
    elements = [
        _div(f"**Investigating…**\n\n> {safe}"),
        _div("_This card will update as I work._"),
    ]
    return _shell(
        header=_header(title="IncidentFox Investigation", template="blue"),
        elements=elements,
    )


def build_streaming_card(*, prompt: str, partial_text: str) -> CardDict:
    safe_prompt = escape_lark_md(prompt)
    chunks = split_for_card_chunks(to_lark_md(partial_text))
    elements: list[dict[str, Any]] = [_div(f"**Investigating…**\n\n> {safe_prompt}"), _hr()]
    for chunk in chunks:
        elements.append(_div(chunk))
    return _shell(
        header=_header(title="IncidentFox Investigation", template="blue"),
        elements=elements,
    )


def build_final_card(*, prompt: str, result_text: str, success: bool) -> CardDict:
    safe_prompt = escape_lark_md(prompt)
    chunks = split_for_card_chunks(to_lark_md(result_text))
    elements: list[dict[str, Any]] = [_div(f"**Question**\n\n> {safe_prompt}"), _hr()]
    for chunk in chunks:
        elements.append(_div(chunk))
    template = "green" if success else "red"
    title = "Investigation Complete" if success else "Investigation Failed"
    return _shell(header=_header(title=title, template=template), elements=elements)


def build_error_card(*, prompt: str, error: str) -> CardDict:
    safe_prompt = escape_lark_md(prompt)
    safe_err = escape_lark_md(error)
    elements = [
        _div(f"**Question**\n\n> {safe_prompt}"),
        _hr(),
        _div(f"**Error:** {safe_err}"),
    ]
    return _shell(header=_header(title="Investigation Failed", template="red"), elements=elements)
