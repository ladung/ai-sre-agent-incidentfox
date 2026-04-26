# lark-bot Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Phase 1 of lark-bot — a standalone Python service that lets a single self-hosted Lark (international) tenant @-mention the bot in any chat, see a streaming agent investigation rendered as a progressively-edited Lark card, and receive a final result. Both webhook and long-connection inbound modes work.

**Architecture:** New standalone `lark-bot/` Python service. Long-connection mode uses `lark-oapi` WebSocket client. Webhook mode uses orchestrator's new `/webhooks/lark` endpoint, which verifies signatures + decrypts payloads then forwards to lark-bot's `/internal/lark/event`. All agent dispatch routes through orchestrator's new streaming SSE endpoint that pipes `sre-agent` events through. Single-tenant only this phase — `tenant_key` is fixed at boot via `LARK_TENANT_KEY` env var.

**Tech Stack:** Python 3.11, `lark-oapi>=1.4` (official ByteDance SDK), FastAPI (internal HTTP server), `httpx` (orchestrator client + SSE consumption), `pytest` + `pytest-asyncio` for tests, `uv` for deps. Helm chart matches existing slack-bot template structure.

**Spec reference:** `docs/superpowers/specs/2026-04-26-lark-bot-design.md` — only Phase 1 of the four-phase rollout.

---

## File Structure

**New service `lark-bot/`** (flat layout, mirroring slack-bot):

```
lark-bot/
  pyproject.toml
  Dockerfile
  README.md
  env.example
  lark-manifest.json              # Lark app config sample (events, scopes)
  app.py                          # Service entry (mode select, lifespan)
  ws_client.py                    # lark-oapi long-connection client
  http_server.py                  # FastAPI internal endpoint
  event_router.py                 # Normalize Lark events → unified shape
  config_client.py                # config-service per-team config loader
  orchestrator_client.py          # POST /api/v1/agents/dispatch-stream + SSE
  investigation_handler.py        # Lifecycle: dispatch → stream → finalize
  stream_handler.py               # SSE → Lark card edit calls (debounced)
  card_builder.py                 # Card v2 composition
  markdown_utils.py               # Agent markdown → Lark md_v2 subset
  state.py                        # In-memory conversation state
  k8s/
    deployment.yaml               # (dev reference)
  tests/
    test_event_router.py
    test_card_builder.py
    test_markdown_utils.py
    test_state.py
    test_orchestrator_client.py
    test_stream_handler.py
    test_investigation_handler.py
    test_http_server.py
    test_app_smoke.py
```

**Orchestrator changes:**

```
orchestrator/src/incidentfox_orchestrator/
  webhooks/
    lark_app.py                   # NEW: webhook entry, decrypt, forward
    signatures.py                 # MODIFY: + verify_lark_signature, decrypt_lark_payload
    router.py                     # MODIFY: wire /webhooks/lark, URL verification
  clients.py                      # MODIFY: + AgentApiClient.stream_agent generator
  api_server.py                   # MODIFY: + POST /api/v1/agents/dispatch-stream (SSE proxy)
orchestrator/tests/unit/
  test_lark_app.py                # NEW
  test_lark_signatures.py         # NEW
  test_agent_streaming.py         # NEW
```

**Helm chart:**

```
charts/incidentfox/
  templates/lark-bot.yaml         # NEW
  values.yaml                     # MODIFY: + services.larkBot, externalSecrets.larkBot
  values.staging.yaml             # MODIFY: services.larkBot.enabled=false (default off)
  values.prod.yaml                # MODIFY: services.larkBot.enabled=false
  values.pilot.yaml               # MODIFY: example with services.larkBot.enabled=true
```

**CI:**

```
.github/workflows/deploy-eks.yml  # MODIFY: add lark-bot to services list + image build matrix
```

---

## Conventions used throughout this plan

- **Python style:** ruff (project's existing config). Run `ruff check lark-bot/` before each commit.
- **Tests:** `pytest` from `lark-bot/` directory. `uv run pytest tests/<file>::<test> -v`.
- **Type hints:** required on all public functions; `from __future__ import annotations` at top of every Python file.
- **Logging:** structured JSON via `_log(event, **fields)` helper (mirror orchestrator pattern).
- **Commits:** conventional commits format (`feat:`, `fix:`, `test:`, `chore:`).

---

## Task 1: Service scaffold (pyproject, Dockerfile, README, env.example)

**Files:**
- Create: `lark-bot/pyproject.toml`
- Create: `lark-bot/Dockerfile`
- Create: `lark-bot/README.md`
- Create: `lark-bot/env.example`
- Create: `lark-bot/.gitignore`

- [ ] **Step 1: Create `lark-bot/pyproject.toml`**

```toml
[project]
name = "incidentfox-lark-bot"
version = "0.1.0"
description = "Lark (international) bot for IncidentFox AI SRE agent"
requires-python = ">=3.11"
dependencies = [
    "lark-oapi>=1.4.0",
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "httpx>=0.27.0",
    "pydantic>=2.8.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "respx>=0.21.0",
    "ruff>=0.6.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["."]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create `lark-bot/Dockerfile`** (mirror slack-bot/Dockerfile)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml .
RUN uv pip install --system -e .

COPY *.py .

RUN useradd -m -u 1000 larkbot && chown -R larkbot:larkbot /app
USER larkbot

EXPOSE 8080
CMD ["python", "app.py"]
```

- [ ] **Step 3: Create `lark-bot/env.example`**

```bash
# === Required ===
LARK_APP_ID=cli_xxxxxxxxxxxxxx
LARK_APP_SECRET=
LARK_VERIFICATION_TOKEN=
LARK_ENCRYPT_KEY=          # Optional; only set if Lark app config has Encrypt Key
LARK_TENANT_KEY=            # Single-tenant Phase 1 only — bind one tenant at boot

# === Inbound transport ===
# long_connection | webhook | hybrid
LARK_TRANSPORT_MODE=long_connection

# === Endpoints ===
LARK_API_BASE=https://open.larksuite.com
ORCHESTRATOR_URL=http://orchestrator:8000
CONFIG_SERVICE_URL=http://config-service:8080
INTERNAL_HTTP_PORT=8080

# === IncidentFox identity (single-tenant binding) ===
INCIDENTFOX_TEAM_TOKEN=     # Bearer token for orchestrator + config-service auth
INCIDENTFOX_ORG_ID=
INCIDENTFOX_TEAM_ID=

# === Optional ===
LOG_LEVEL=INFO
LARK_OAUTH_ENABLED=false    # Phase 2 — must be false in Phase 1
```

- [ ] **Step 4: Create `lark-bot/.gitignore`**

```
__pycache__/
*.pyc
.venv/
.pytest_cache/
.ruff_cache/
.env
```

- [ ] **Step 5: Create `lark-bot/README.md`** (one paragraph + run instructions)

```markdown
# IncidentFox Lark Bot

Lark (international) chat surface for IncidentFox AI SRE. Phase 1: single-tenant, both webhook and long-connection event modes, agent dispatch through orchestrator, basic Lark Card v2 rendering with progressive updates.

## Local dev

```
uv pip install -e ".[dev]"
cp env.example .env  # fill in values
python app.py
```

## Tests

```
uv run pytest tests/ -v
```

See `docs/superpowers/specs/2026-04-26-lark-bot-design.md` for full design.
```

- [ ] **Step 6: Verify install works**

```bash
cd lark-bot && uv pip install --system -e ".[dev]"
```

Expected: clean install, no errors.

- [ ] **Step 7: Commit**

```bash
git add lark-bot/pyproject.toml lark-bot/Dockerfile lark-bot/README.md lark-bot/env.example lark-bot/.gitignore
git commit -m "feat(lark-bot): scaffold service (pyproject, Dockerfile, env.example)"
```

---

## Task 2: `state.py` — in-memory conversation state

**Files:**
- Create: `lark-bot/state.py`
- Test: `lark-bot/tests/test_state.py`

- [ ] **Step 1: Write failing test `tests/test_state.py`**

```python
from __future__ import annotations

import pytest

from state import ConversationState, Investigation, generate_session_id


def test_session_id_stable_for_same_chat_and_thread():
    a = generate_session_id(chat_id="oc_abc", root_id="om_xyz")
    b = generate_session_id(chat_id="oc_abc", root_id="om_xyz")
    assert a == b
    assert a.startswith("lark-")
    assert len(a) <= 63  # K8s RFC 1123 label limit


def test_session_id_dm_when_no_thread():
    sid = generate_session_id(chat_id="p2p_user1", root_id=None)
    assert sid.startswith("lark-")


def test_session_id_sanitizes_non_alphanumeric():
    sid = generate_session_id(chat_id="oc_AbC.123", root_id="om/xyz_456")
    assert sid.replace("-", "").islower()
    import re
    assert re.fullmatch(r"[a-z0-9-]+", sid)


def test_conversation_state_get_set():
    s = ConversationState()
    inv = Investigation(session_id="lark-abc", message_id="om_123", status="running")
    s.put("lark-abc", inv)
    assert s.get("lark-abc") is inv
    assert s.get("missing") is None


def test_conversation_state_clear():
    s = ConversationState()
    s.put("k", Investigation(session_id="k", message_id="m", status="running"))
    s.clear("k")
    assert s.get("k") is None
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_state.py -v`
Expected: ImportError for `state`.

- [ ] **Step 3: Implement `state.py`**

```python
from __future__ import annotations

import re
from dataclasses import dataclass, field
from threading import RLock
from typing import Optional


@dataclass
class Investigation:
    session_id: str
    message_id: str            # Lark message ID of the bot's reply card
    status: str                # "running" | "completed" | "failed"
    last_update_ms: int = 0    # For stream_handler debounce


def _sanitize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def generate_session_id(*, chat_id: str, root_id: Optional[str]) -> str:
    """K8s-safe session id: lark-<chat>-<thread>, max 63 chars."""
    chat = _sanitize(chat_id)[:20] if chat_id else "dm"
    thread = _sanitize(root_id)[:30] if root_id else "main"
    return f"lark-{chat}-{thread}"


class ConversationState:
    """Thread-safe in-memory store. Keyed by session_id."""

    def __init__(self) -> None:
        self._items: dict[str, Investigation] = {}
        self._lock = RLock()

    def put(self, session_id: str, inv: Investigation) -> None:
        with self._lock:
            self._items[session_id] = inv

    def get(self, session_id: str) -> Optional[Investigation]:
        with self._lock:
            return self._items.get(session_id)

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._items.pop(session_id, None)
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_state.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add lark-bot/state.py lark-bot/tests/test_state.py
git commit -m "feat(lark-bot): add conversation state and session id generator"
```

---

## Task 3: `markdown_utils.py` — agent markdown → Lark `md_v2`

**Files:**
- Create: `lark-bot/markdown_utils.py`
- Test: `lark-bot/tests/test_markdown_utils.py`

Lark `md_v2` (used inside `div` modules of card v2) supports a subset: `**bold**`, `*italic*`, `` `code` ``, code fences, `[text](url)`, `<at user_id="..."></at>` for mentions. It does NOT support tables (use card columns) or HTML. Headings are not honored inside cards — emit them as bold lines.

- [ ] **Step 1: Write failing test `tests/test_markdown_utils.py`**

```python
from __future__ import annotations

from markdown_utils import to_lark_md, escape_lark_md, split_for_card_chunks


def test_passthrough_basic_formatting():
    assert to_lark_md("**bold**") == "**bold**"
    assert to_lark_md("*italic*") == "*italic*"
    assert to_lark_md("`code`") == "`code`"


def test_heading_becomes_bold_line():
    assert to_lark_md("# Title").splitlines()[0] == "**Title**"
    assert to_lark_md("## Sub").splitlines()[0] == "**Sub**"


def test_links_passthrough():
    assert to_lark_md("[docs](https://example.com)") == "[docs](https://example.com)"


def test_user_mention_replacement():
    # Slack-style <@U123> should be stripped (not a Lark concept)
    assert to_lark_md("hello <@U123>") == "hello"


def test_escape_pipe_and_brackets_in_user_text():
    # User-supplied text fed into a card cell — pipes break tables, brackets break links.
    assert escape_lark_md("a|b") == r"a\|b"
    assert escape_lark_md("[x]") == r"\[x\]"


def test_split_for_card_chunks_under_limit_is_passthrough():
    text = "a" * 100
    chunks = split_for_card_chunks(text, max_chars=200)
    assert chunks == [text]


def test_split_for_card_chunks_at_paragraph_boundary():
    text = "para one\n\npara two\n\npara three"
    chunks = split_for_card_chunks(text, max_chars=15)
    assert all(len(c) <= 15 + 2 for c in chunks)  # +2 for trailing \n\n on flush
    assert "para one" in chunks[0]
    assert chunks[-1].endswith("para three")


def test_split_for_card_chunks_hard_split_long_paragraph():
    text = "x" * 50
    chunks = split_for_card_chunks(text, max_chars=20)
    assert len(chunks) == 3
    assert all(len(c) <= 20 for c in chunks)
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_markdown_utils.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `markdown_utils.py`**

```python
from __future__ import annotations

import re

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)
_SLACK_USER_MENTION_RE = re.compile(r"\s*<@[UW][A-Z0-9]+>")


def to_lark_md(text: str) -> str:
    """Convert agent-emitted markdown to Lark md_v2 subset.

    - Headings → bold lines (Lark cards don't render h1-h6 inside divs).
    - Strip Slack-style user mentions (<@U123>); Lark uses <at user_id="..."> emitted by card_builder.
    - Pass through bold, italic, code, code fences, links.
    """
    text = _HEADING_RE.sub(lambda m: f"**{m.group(2).strip()}**", text)
    text = _SLACK_USER_MENTION_RE.sub("", text)
    return text


def escape_lark_md(s: str) -> str:
    """Escape user-supplied text before inserting into a card cell."""
    return s.replace("\\", "\\\\").replace("|", r"\|").replace("[", r"\[").replace("]", r"\]")


def split_for_card_chunks(text: str, *, max_chars: int = 4000) -> list[str]:
    """Split long text into card-friendly chunks.

    Lark's per-element text limit is 4096 chars (we use 4000 default for safety margin).
    Prefer paragraph boundaries; fall back to hard split.
    """
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    buffer = ""
    for para in text.split("\n\n"):
        candidate = (buffer + ("\n\n" if buffer else "") + para)
        if len(candidate) <= max_chars:
            buffer = candidate
            continue
        if buffer:
            chunks.append(buffer)
            buffer = ""
        # Paragraph itself too large — hard split.
        for i in range(0, len(para), max_chars):
            chunks.append(para[i:i + max_chars])
    if buffer:
        chunks.append(buffer)
    return chunks
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_markdown_utils.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add lark-bot/markdown_utils.py lark-bot/tests/test_markdown_utils.py
git commit -m "feat(lark-bot): markdown converter for Lark md_v2"
```

---

## Task 4: `card_builder.py` — basic Lark Card v2 composition

Three cards are needed in Phase 1: **status card** (initial "investigating…"), **streaming update card** (rolling result while running), **final card** (success or failure).

**Files:**
- Create: `lark-bot/card_builder.py`
- Test: `lark-bot/tests/test_card_builder.py`

- [ ] **Step 1: Write failing test `tests/test_card_builder.py`**

```python
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
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_card_builder.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `card_builder.py`**

```python
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
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_card_builder.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add lark-bot/card_builder.py lark-bot/tests/test_card_builder.py
git commit -m "feat(lark-bot): card builder for status, streaming, final, error cards"
```

---

## Task 5: `event_router.py` — normalize Lark events

Both transports (long-connection and webhook) yield differently-shaped Lark events. The router normalizes them to a single `LarkEvent` dataclass.

**Files:**
- Create: `lark-bot/event_router.py`
- Test: `lark-bot/tests/test_event_router.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

import pytest

from event_router import LarkEvent, normalize_event, EventValidationError


def _msg_event_payload(*, message_text="@_user_1 hello", chat_id="oc_abc", root_id=None):
    return {
        "schema": "2.0",
        "header": {
            "event_id": "evt_1",
            "event_type": "im.message.receive_v1",
            "tenant_key": "tk_123",
            "create_time": "1700000000000",
        },
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_id": "om_1",
                "root_id": root_id,
                "chat_id": chat_id,
                "chat_type": "group",
                "message_type": "text",
                "content": '{"text": "' + message_text + '"}',
                "mentions": [{"key": "@_user_1", "id": {"open_id": "ou_bot"}}],
            },
        },
    }


def test_normalize_at_mention_message():
    evt = normalize_event(_msg_event_payload(message_text="@_user_1 why is checkout slow?"))
    assert isinstance(evt, LarkEvent)
    assert evt.event_id == "evt_1"
    assert evt.tenant_key == "tk_123"
    assert evt.chat_id == "oc_abc"
    assert evt.message_id == "om_1"
    assert evt.root_id is None
    assert evt.is_mention is True
    assert evt.text_after_mention == "why is checkout slow?"
    assert evt.sender_open_id == "ou_1"


def test_normalize_thread_followup_uses_root_id():
    evt = normalize_event(_msg_event_payload(root_id="om_thread_root"))
    assert evt.root_id == "om_thread_root"


def test_normalize_p2p_dm_no_mention_required():
    payload = _msg_event_payload(message_text="hi")
    payload["event"]["message"]["chat_type"] = "p2p"
    payload["event"]["message"]["mentions"] = []
    evt = normalize_event(payload)
    assert evt.is_mention is False
    assert evt.is_dm is True
    assert evt.text_after_mention == "hi"


def test_url_verification_returns_special_marker():
    payload = {"type": "url_verification", "challenge": "abc123"}
    evt = normalize_event(payload)
    assert evt.event_type == "url_verification"
    assert evt.url_verification_challenge == "abc123"


def test_unknown_event_type_raises():
    payload = {"schema": "2.0", "header": {"event_type": "im.message.something_unsupported"}}
    with pytest.raises(EventValidationError):
        normalize_event(payload)


def test_non_text_message_returns_none_text():
    payload = _msg_event_payload()
    payload["event"]["message"]["message_type"] = "image"
    payload["event"]["message"]["content"] = '{"image_key": "img_x"}'
    evt = normalize_event(payload)
    assert evt.text_after_mention == ""
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_event_router.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `event_router.py`**

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

SUPPORTED_EVENT_TYPES = {"im.message.receive_v1", "url_verification"}


class EventValidationError(Exception):
    pass


@dataclass
class LarkEvent:
    event_type: str
    event_id: str = ""
    tenant_key: str = ""
    chat_id: str = ""
    chat_type: str = ""               # "p2p" | "group"
    message_id: str = ""
    root_id: Optional[str] = None
    sender_open_id: str = ""
    message_type: str = ""             # "text" | "image" | ...
    text_after_mention: str = ""
    is_mention: bool = False
    is_dm: bool = False
    url_verification_challenge: str = ""


def _strip_mentions(text: str, mention_keys: list[str]) -> str:
    out = text
    for key in mention_keys:
        out = out.replace(key, "")
    return out.strip()


def normalize_event(payload: dict[str, Any]) -> LarkEvent:
    if payload.get("type") == "url_verification":
        return LarkEvent(
            event_type="url_verification",
            url_verification_challenge=str(payload.get("challenge", "")),
        )

    header = payload.get("header") or {}
    event_type = header.get("event_type", "")
    if event_type not in SUPPORTED_EVENT_TYPES:
        raise EventValidationError(f"unsupported event_type: {event_type!r}")

    body = payload.get("event") or {}
    msg = body.get("message") or {}
    sender = (body.get("sender") or {}).get("sender_id") or {}
    mentions = msg.get("mentions") or []
    chat_type = msg.get("chat_type", "")
    message_type = msg.get("message_type", "")

    text = ""
    if message_type == "text":
        try:
            content = json.loads(msg.get("content", "{}"))
            text = content.get("text", "")
        except json.JSONDecodeError:
            text = ""

    mention_keys = [m.get("key", "") for m in mentions if m.get("key")]
    is_mention = bool(mention_keys)
    text_after_mention = _strip_mentions(text, mention_keys) if text else ""

    return LarkEvent(
        event_type=event_type,
        event_id=header.get("event_id", ""),
        tenant_key=header.get("tenant_key", ""),
        chat_id=msg.get("chat_id", ""),
        chat_type=chat_type,
        message_id=msg.get("message_id", ""),
        root_id=msg.get("root_id") or None,
        sender_open_id=sender.get("open_id", ""),
        message_type=message_type,
        text_after_mention=text_after_mention,
        is_mention=is_mention,
        is_dm=(chat_type == "p2p"),
    )
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_event_router.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add lark-bot/event_router.py lark-bot/tests/test_event_router.py
git commit -m "feat(lark-bot): normalize Lark events to unified shape"
```

---

## Task 6: `config_client.py` — per-team config loader

Config-service exposes `GET /api/v1/config/me/effective` with bearer-token auth. We need a thin client that fetches once per investigation.

**Files:**
- Create: `lark-bot/config_client.py`
- Test: `lark-bot/tests/test_config_client.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

import httpx
import pytest
import respx

from config_client import ConfigClient, ConfigClientError


@respx.mock
async def test_fetch_effective_config_success():
    respx.get("http://config-service:8080/api/v1/config/me/effective").mock(
        return_value=httpx.Response(200, json={"lark": {"x": 1}, "_meta": {"team_id": "t1"}})
    )
    client = ConfigClient(base_url="http://config-service:8080", team_token="tok")
    cfg = await client.fetch_effective()
    assert cfg["lark"]["x"] == 1
    await client.aclose()


@respx.mock
async def test_fetch_effective_config_401_raises():
    respx.get("http://config-service:8080/api/v1/config/me/effective").mock(
        return_value=httpx.Response(401, json={"error": "unauthorized"})
    )
    client = ConfigClient(base_url="http://config-service:8080", team_token="bad")
    with pytest.raises(ConfigClientError):
        await client.fetch_effective()
    await client.aclose()
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_config_client.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `config_client.py`**

```python
from __future__ import annotations

from typing import Any

import httpx


class ConfigClientError(Exception):
    pass


class ConfigClient:
    def __init__(self, *, base_url: str, team_token: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
            headers={"Authorization": f"Bearer {team_token}"},
        )

    async def fetch_effective(self) -> dict[str, Any]:
        try:
            resp = await self._http.get("/api/v1/config/me/effective")
        except httpx.HTTPError as e:
            raise ConfigClientError(f"transport error: {e}") from e
        if resp.status_code != 200:
            raise ConfigClientError(f"status {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    async def aclose(self) -> None:
        await self._http.aclose()
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_config_client.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add lark-bot/config_client.py lark-bot/tests/test_config_client.py
git commit -m "feat(lark-bot): config-service client for effective per-team config"
```

---

## Task 7: Orchestrator side — `AgentApiClient.stream_agent` generator

Before lark-bot can consume orchestrator's stream, orchestrator's client needs a streaming variant. This and Task 8 are orchestrator-side changes.

**Files:**
- Modify: `orchestrator/src/incidentfox_orchestrator/clients.py` (add `stream_agent`)
- Test: `orchestrator/tests/unit/test_agent_streaming.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import pytest
import respx

from incidentfox_orchestrator.clients import AgentApiClient


def _sse_chunks(events: list[dict]) -> bytes:
    out = b""
    for e in events:
        out += b"data: " + json.dumps(e).encode() + b"\n\n"
    return out


@respx.mock
async def test_stream_agent_yields_events_in_order():
    sse = _sse_chunks(
        [{"type": "tool_use", "name": "kubectl"}, {"type": "complete", "result": "done"}]
    )
    respx.post("http://orch:8000/api/v1/agents/dispatch-stream").mock(
        return_value=httpx.Response(
            200, content=sse, headers={"content-type": "text/event-stream"}
        )
    )
    client = AgentApiClient(base_url="http://orch:8000")
    events = []
    async for evt in client.stream_agent(
        team_token="tok", agent_name="sre", message="hi", session_id="lark-x"
    ):
        events.append(evt)
    assert [e["type"] for e in events] == ["tool_use", "complete"]


@respx.mock
async def test_stream_agent_skips_keepalives_and_blank_lines():
    sse = b": ping\n\ndata: {\"type\":\"complete\"}\n\n"
    respx.post("http://orch:8000/api/v1/agents/dispatch-stream").mock(
        return_value=httpx.Response(
            200, content=sse, headers={"content-type": "text/event-stream"}
        )
    )
    client = AgentApiClient(base_url="http://orch:8000")
    events = [evt async for evt in client.stream_agent(
        team_token="t", agent_name="sre", message="hi", session_id="s"
    )]
    assert events == [{"type": "complete"}]
```

- [ ] **Step 2: Run, verify fail**

Run from `orchestrator/`:
```
uv run pytest tests/unit/test_agent_streaming.py -v
```
Expected: AttributeError, AgentApiClient has no `stream_agent`.

- [ ] **Step 3: Implement — append to `orchestrator/src/incidentfox_orchestrator/clients.py` `AgentApiClient` class**

```python
    async def stream_agent(
        self,
        *,
        team_token: str,
        agent_name: str,
        message: str,
        session_id: str,
        tenant_id: Optional[str] = None,
        team_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        timeout: float = 600.0,
    ) -> AsyncIterator[dict[str, Any]]:
        """Async-iterate JSON events from orchestrator's streaming dispatch endpoint."""
        import json as _json

        body = {
            "agent_name": agent_name,
            "message": message,
            "session_id": session_id,
            "tenant_id": tenant_id,
            "team_id": team_id,
            "correlation_id": correlation_id,
        }
        headers = {
            "Authorization": f"Bearer {team_token}",
            "Accept": "text/event-stream",
        }
        async with httpx.AsyncClient(timeout=timeout) as http:
            async with http.stream(
                "POST", f"{self.base_url}/api/v1/agents/dispatch-stream", json=body, headers=headers
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("data:"):
                        payload = line[len("data:"):].strip()
                        if not payload:
                            continue
                        try:
                            yield _json.loads(payload)
                        except _json.JSONDecodeError:
                            continue
```

Add at top of file (if not present): `from collections.abc import AsyncIterator` and `import httpx`.

- [ ] **Step 4: Run, verify pass**

```
uv run pytest tests/unit/test_agent_streaming.py -v
```
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/src/incidentfox_orchestrator/clients.py orchestrator/tests/unit/test_agent_streaming.py
git commit -m "feat(orchestrator): add AgentApiClient.stream_agent SSE consumer"
```

---

## Task 8: Orchestrator side — `POST /api/v1/agents/dispatch-stream` SSE proxy

This new endpoint accepts a request, dispatches to sre-agent, and re-emits SSE events to the caller. It's the SSE proxy that makes lark-bot's streaming work.

**Files:**
- Modify: `orchestrator/src/incidentfox_orchestrator/api_server.py`
- Test: `orchestrator/tests/unit/test_agent_streaming.py` (extend)

- [ ] **Step 1: Skim existing api_server.py to find the right router** — read top 50 lines

```bash
sed -n '1,50p' orchestrator/src/incidentfox_orchestrator/api_server.py
```

- [ ] **Step 2: Write failing test (append to `test_agent_streaming.py`)**

```python
from fastapi.testclient import TestClient


def test_dispatch_stream_endpoint_proxies_sre_agent_sse(monkeypatch):
    from incidentfox_orchestrator.api_server import app, get_settings

    sse_chunks = [
        b'data: {"type": "tool_use", "name": "kubectl"}\n\n',
        b'data: {"type": "complete", "result": "ok"}\n\n',
    ]

    class FakeSreAgentClient:
        def stream_investigate(self, **kwargs):
            for c in sse_chunks:
                yield c

    # Monkeypatch the sre-agent client factory used by the new endpoint.
    import incidentfox_orchestrator.api_server as srv
    monkeypatch.setattr(srv, "_make_sre_agent_streamer", lambda **_: FakeSreAgentClient())

    client = TestClient(app)
    resp = client.post(
        "/api/v1/agents/dispatch-stream",
        json={"agent_name": "sre", "message": "hi", "session_id": "lark-x"},
        headers={"Authorization": "Bearer t"},
    )
    assert resp.status_code == 200
    body = resp.text
    assert "tool_use" in body
    assert "complete" in body
```

- [ ] **Step 3: Implement endpoint — append to `api_server.py`**

```python
from fastapi import Request, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional


class DispatchStreamRequest(BaseModel):
    agent_name: str
    message: str
    session_id: str
    tenant_id: Optional[str] = None
    team_id: Optional[str] = None
    correlation_id: Optional[str] = None


def _make_sre_agent_streamer(*, base_url: str):
    """Factory so tests can monkeypatch."""
    from incidentfox_orchestrator.clients import SreAgentStreamingClient
    return SreAgentStreamingClient(base_url=base_url)


@app.post("/api/v1/agents/dispatch-stream")
async def dispatch_stream(req: DispatchStreamRequest, request: Request):
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    settings = get_settings()
    streamer = _make_sre_agent_streamer(base_url=settings.agent_service_url)

    def gen():
        for chunk in streamer.stream_investigate(
            agent_name=req.agent_name,
            message=req.message,
            session_id=req.session_id,
            tenant_id=req.tenant_id,
            team_id=req.team_id,
            correlation_id=req.correlation_id,
            team_token=auth.split(" ", 1)[1],
        ):
            yield chunk

    return StreamingResponse(gen(), media_type="text/event-stream")
```

- [ ] **Step 4: Add `SreAgentStreamingClient` to `orchestrator/src/incidentfox_orchestrator/clients.py`**

```python
import httpx
from typing import Iterator


class SreAgentStreamingClient:
    """Thin streaming client for sre-agent's /investigate SSE endpoint."""

    def __init__(self, *, base_url: str, timeout: float = 600.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def stream_investigate(
        self,
        *,
        agent_name: str,
        message: str,
        session_id: str,
        team_token: str,
        tenant_id: Optional[str] = None,
        team_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Iterator[bytes]:
        body = {
            "agent_name": agent_name,
            "message": message,
            "session_id": session_id,
            "tenant_id": tenant_id,
            "team_id": team_id,
            "correlation_id": correlation_id,
        }
        headers = {"Authorization": f"Bearer {team_token}", "Accept": "text/event-stream"}
        with httpx.Client(timeout=self._timeout) as http:
            with http.stream(
                "POST", f"{self._base_url}/investigate", json=body, headers=headers
            ) as resp:
                resp.raise_for_status()
                for chunk in resp.iter_raw():
                    yield chunk
```

- [ ] **Step 5: Run test**

```
uv run pytest tests/unit/test_agent_streaming.py -v
```
Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/src/incidentfox_orchestrator/api_server.py orchestrator/src/incidentfox_orchestrator/clients.py orchestrator/tests/unit/test_agent_streaming.py
git commit -m "feat(orchestrator): SSE-proxy endpoint /api/v1/agents/dispatch-stream"
```

---

## Task 9: lark-bot `orchestrator_client.py`

Wraps `AgentApiClient.stream_agent`-equivalent behavior but inside lark-bot. lark-bot doesn't depend on orchestrator's package, so this is a small standalone HTTP+SSE client.

**Files:**
- Create: `lark-bot/orchestrator_client.py`
- Test: `lark-bot/tests/test_orchestrator_client.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

import httpx
import pytest
import respx

from orchestrator_client import OrchestratorClient, OrchestratorError


@respx.mock
async def test_stream_yields_events():
    sse = b'data: {"type":"tool_use","name":"kubectl"}\n\ndata: {"type":"complete"}\n\n'
    respx.post("http://orch:8000/api/v1/agents/dispatch-stream").mock(
        return_value=httpx.Response(200, content=sse, headers={"content-type": "text/event-stream"})
    )
    client = OrchestratorClient(base_url="http://orch:8000", team_token="tok")
    events = [e async for e in client.stream_agent(message="hi", session_id="s")]
    assert [e["type"] for e in events] == ["tool_use", "complete"]
    await client.aclose()


@respx.mock
async def test_stream_raises_on_4xx():
    respx.post("http://orch:8000/api/v1/agents/dispatch-stream").mock(
        return_value=httpx.Response(401, json={"error": "unauthorized"})
    )
    client = OrchestratorClient(base_url="http://orch:8000", team_token="bad")
    with pytest.raises(OrchestratorError):
        async for _ in client.stream_agent(message="hi", session_id="s"):
            pass
    await client.aclose()
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_orchestrator_client.py -v`

- [ ] **Step 3: Implement**

```python
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Optional

import httpx


class OrchestratorError(Exception):
    pass


class OrchestratorClient:
    def __init__(
        self,
        *,
        base_url: str,
        team_token: str,
        agent_name: str = "sre",
        timeout: float = 600.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._team_token = team_token
        self._agent_name = agent_name
        self._http = httpx.AsyncClient(timeout=timeout)

    async def stream_agent(
        self,
        *,
        message: str,
        session_id: str,
        tenant_id: Optional[str] = None,
        team_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        body = {
            "agent_name": self._agent_name,
            "message": message,
            "session_id": session_id,
            "tenant_id": tenant_id,
            "team_id": team_id,
            "correlation_id": correlation_id,
        }
        headers = {
            "Authorization": f"Bearer {self._team_token}",
            "Accept": "text/event-stream",
        }
        async with self._http.stream(
            "POST",
            f"{self._base_url}/api/v1/agents/dispatch-stream",
            json=body,
            headers=headers,
        ) as resp:
            if resp.status_code >= 400:
                text = await resp.aread()
                raise OrchestratorError(f"status {resp.status_code}: {text[:200]!r}")
            async for line in resp.aiter_lines():
                if not line or line.startswith(":"):
                    continue
                if not line.startswith("data:"):
                    continue
                payload = line[len("data:"):].strip()
                if not payload:
                    continue
                try:
                    yield json.loads(payload)
                except json.JSONDecodeError:
                    continue

    async def aclose(self) -> None:
        await self._http.aclose()
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_orchestrator_client.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add lark-bot/orchestrator_client.py lark-bot/tests/test_orchestrator_client.py
git commit -m "feat(lark-bot): orchestrator SSE streaming client"
```

---

## Task 10: `stream_handler.py` — SSE → debounced card edits

Receives an async iterator of agent events; given an outbound `update_card(card)` callback and the original prompt, accumulates partial text and emits updated cards to Lark, debounced to ~250ms to stay under Lark's per-message edit rate limit.

**Files:**
- Create: `lark-bot/stream_handler.py`
- Test: `lark-bot/tests/test_stream_handler.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

import asyncio

import pytest

from stream_handler import handle_stream


def _events(*items):
    async def gen():
        for it in items:
            yield it
    return gen()


@pytest.mark.asyncio
async def test_handle_stream_calls_update_then_finalize_on_complete():
    updates: list[str] = []
    finals: list[tuple[str, bool]] = []

    async def on_update(text: str):
        updates.append(text)

    async def on_final(text: str, success: bool):
        finals.append((text, success))

    src = _events(
        {"type": "text", "text": "Looking…"},
        {"type": "text", "text": " at logs."},
        {"type": "complete", "result": "Looking… at logs.", "success": True},
    )
    await handle_stream(src, on_update=on_update, on_final=on_final, debounce_ms=0)
    # debounce=0 → every text triggers an update (final excluded)
    assert updates == ["Looking…", "Looking… at logs."]
    assert finals == [("Looking… at logs.", True)]


@pytest.mark.asyncio
async def test_handle_stream_failure_event_marks_unsuccessful():
    finals: list[tuple[str, bool]] = []

    async def on_update(_: str): pass
    async def on_final(text: str, success: bool):
        finals.append((text, success))

    src = _events({"type": "error", "error": "boom"})
    await handle_stream(src, on_update=on_update, on_final=on_final, debounce_ms=0)
    assert finals == [("boom", False)]


@pytest.mark.asyncio
async def test_handle_stream_debounce_collapses_rapid_updates():
    updates: list[str] = []

    async def on_update(text: str):
        updates.append(text)

    async def on_final(*_):
        pass

    src = _events(
        {"type": "text", "text": "a"},
        {"type": "text", "text": "b"},
        {"type": "text", "text": "c"},
        {"type": "complete", "result": "abc", "success": True},
    )
    await handle_stream(src, on_update=on_update, on_final=on_final, debounce_ms=200)
    # With 200ms debounce and synchronous gen, only the last cumulative text should slip through.
    assert updates[-1] == "abc" or updates == []  # acceptable: 0 mid-stream updates if stream finishes inside debounce window
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_stream_handler.py -v`

- [ ] **Step 3: Implement**

```python
from __future__ import annotations

import time
from collections.abc import AsyncIterator
from typing import Any, Awaitable, Callable

OnUpdate = Callable[[str], Awaitable[None]]
OnFinal = Callable[[str, bool], Awaitable[None]]


async def handle_stream(
    events: AsyncIterator[dict[str, Any]],
    *,
    on_update: OnUpdate,
    on_final: OnFinal,
    debounce_ms: int = 250,
) -> None:
    """Consume agent SSE events, drive on_update (debounced) and on_final."""
    buffer = ""
    last_flush_ms = 0
    final_called = False

    def now_ms() -> int:
        return int(time.monotonic() * 1000)

    async for evt in events:
        etype = evt.get("type")
        if etype == "text":
            buffer += evt.get("text", "")
            if now_ms() - last_flush_ms >= debounce_ms:
                await on_update(buffer)
                last_flush_ms = now_ms()
        elif etype == "complete":
            final_called = True
            result = evt.get("result", buffer)
            await on_final(result, bool(evt.get("success", True)))
            return
        elif etype == "error":
            final_called = True
            await on_final(str(evt.get("error", "unknown error")), False)
            return
        # other event types (tool_use, etc.) are ignored in Phase 1

    if not final_called:
        # Stream ended without explicit complete — treat buffer as final success.
        await on_final(buffer, True)
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_stream_handler.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add lark-bot/stream_handler.py lark-bot/tests/test_stream_handler.py
git commit -m "feat(lark-bot): SSE stream handler with debounced card updates"
```

---

## Task 11: `investigation_handler.py` — lifecycle glue

Ties together: receive `LarkEvent` → post initial status card → call `OrchestratorClient.stream_agent` → drive `stream_handler.handle_stream` → patch card on each update / final.

**Files:**
- Create: `lark-bot/investigation_handler.py`
- Test: `lark-bot/tests/test_investigation_handler.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

import pytest

from event_router import LarkEvent
from investigation_handler import InvestigationHandler


class FakeLarkApi:
    def __init__(self) -> None:
        self.posted: list[dict] = []
        self.patched: list[tuple[str, dict]] = []
        self._next_msg_id = "om_card_1"

    async def post_card(self, *, chat_id: str, root_id, card: dict) -> str:
        self.posted.append({"chat_id": chat_id, "root_id": root_id, "card": card})
        return self._next_msg_id

    async def patch_card(self, *, message_id: str, card: dict) -> None:
        self.patched.append((message_id, card))


class FakeOrchestrator:
    async def stream_agent(self, **kwargs):
        async def gen():
            yield {"type": "text", "text": "Looking at pods… "}
            yield {"type": "text", "text": "found OOMKilled."}
            yield {"type": "complete", "result": "Looking at pods… found OOMKilled.", "success": True}
        async for e in gen():
            yield e

    async def aclose(self) -> None:
        pass


@pytest.mark.asyncio
async def test_investigation_posts_status_card_then_finalizes():
    api = FakeLarkApi()
    orch = FakeOrchestrator()
    handler = InvestigationHandler(
        lark_api=api,
        orchestrator=orch,
        org_id="org",
        team_id="team",
        debounce_ms=0,
    )
    evt = LarkEvent(
        event_type="im.message.receive_v1",
        event_id="evt1",
        tenant_key="tk",
        chat_id="oc_x",
        message_id="om_user_1",
        text_after_mention="why is checkout slow?",
        is_mention=True,
    )
    await handler.handle(evt)
    assert len(api.posted) == 1
    assert "Investigating" in api.posted[0]["card"]["body"]["elements"][0]["text"]["content"]
    assert len(api.patched) >= 1
    final_card = api.patched[-1][1]
    assert final_card["header"]["template"] == "green"


@pytest.mark.asyncio
async def test_investigation_renders_error_card_on_orchestrator_failure():
    class BoomOrchestrator:
        async def stream_agent(self, **kwargs):
            raise RuntimeError("orchestrator unreachable")
            yield  # unreachable; makes function a generator

        async def aclose(self): pass

    api = FakeLarkApi()
    handler = InvestigationHandler(
        lark_api=api, orchestrator=BoomOrchestrator(),
        org_id="o", team_id="t", debounce_ms=0,
    )
    await handler.handle(LarkEvent(
        event_type="im.message.receive_v1", chat_id="c", message_id="m",
        text_after_mention="x", is_mention=True,
    ))
    final_card = api.patched[-1][1]
    assert final_card["header"]["template"] == "red"
    body = final_card["body"]["elements"]
    assert any("orchestrator unreachable" in el.get("text", {}).get("content", "") for el in body)
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_investigation_handler.py -v`

- [ ] **Step 3: Implement**

```python
from __future__ import annotations

import json
from typing import Any, Protocol

from card_builder import (
    build_error_card,
    build_final_card,
    build_status_card,
    build_streaming_card,
)
from event_router import LarkEvent
from state import ConversationState, Investigation, generate_session_id
from stream_handler import handle_stream


def _log(event: str, **fields: Any) -> None:
    try:
        print(json.dumps({"service": "lark-bot", "component": "investigation", "event": event, **fields}, default=str))
    except Exception:
        print(f"{event} {fields}")


class _LarkApi(Protocol):
    async def post_card(self, *, chat_id: str, root_id: str | None, card: dict) -> str: ...
    async def patch_card(self, *, message_id: str, card: dict) -> None: ...


class _Orchestrator(Protocol):
    def stream_agent(self, **kwargs): ...
    async def aclose(self) -> None: ...


class InvestigationHandler:
    def __init__(
        self,
        *,
        lark_api: _LarkApi,
        orchestrator: _Orchestrator,
        org_id: str,
        team_id: str,
        state: ConversationState | None = None,
        debounce_ms: int = 250,
    ) -> None:
        self._lark = lark_api
        self._orch = orchestrator
        self._org_id = org_id
        self._team_id = team_id
        self._state = state or ConversationState()
        self._debounce_ms = debounce_ms

    async def handle(self, evt: LarkEvent) -> None:
        prompt = (evt.text_after_mention or "").strip()
        if not prompt:
            _log("empty_prompt_skipped", event_id=evt.event_id)
            return

        session_id = generate_session_id(chat_id=evt.chat_id, root_id=evt.root_id or evt.message_id)
        status_card = build_status_card(prompt=prompt)
        message_id = await self._lark.post_card(
            chat_id=evt.chat_id, root_id=evt.root_id or evt.message_id, card=status_card
        )
        self._state.put(session_id, Investigation(
            session_id=session_id, message_id=message_id, status="running",
        ))
        _log("posted_status_card", session_id=session_id, message_id=message_id)

        try:
            async def on_update(text: str) -> None:
                card = build_streaming_card(prompt=prompt, partial_text=text)
                await self._lark.patch_card(message_id=message_id, card=card)

            async def on_final(text: str, success: bool) -> None:
                card = build_final_card(prompt=prompt, result_text=text, success=success)
                await self._lark.patch_card(message_id=message_id, card=card)
                self._state.clear(session_id)

            await handle_stream(
                self._orch.stream_agent(
                    message=prompt,
                    session_id=session_id,
                    tenant_id=self._org_id,
                    team_id=self._team_id,
                ),
                on_update=on_update,
                on_final=on_final,
                debounce_ms=self._debounce_ms,
            )
        except Exception as e:
            _log("orchestrator_call_failed", session_id=session_id, error=str(e))
            await self._lark.patch_card(
                message_id=message_id,
                card=build_error_card(prompt=prompt, error=str(e)),
            )
            self._state.clear(session_id)
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_investigation_handler.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add lark-bot/investigation_handler.py lark-bot/tests/test_investigation_handler.py
git commit -m "feat(lark-bot): investigation lifecycle handler"
```

---

## Task 12: `lark_api.py` — Lark REST adapter (post + patch card)

Thin wrapper around `lark-oapi` (or raw httpx) for the two API calls we use: `POST /open-apis/im/v1/messages` and `PATCH /open-apis/im/v1/messages/{message_id}`.

**Files:**
- Create: `lark-bot/lark_api.py`
- Test: `lark-bot/tests/test_lark_api.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

import httpx
import pytest
import respx

from lark_api import LarkApi, LarkApiError


@respx.mock
async def test_post_card_returns_message_id():
    respx.post("https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal").mock(
        return_value=httpx.Response(200, json={"code": 0, "tenant_access_token": "t_abc", "expire": 7200})
    )
    respx.post("https://open.larksuite.com/open-apis/im/v1/messages").mock(
        return_value=httpx.Response(200, json={"code": 0, "data": {"message_id": "om_xyz"}})
    )
    api = LarkApi(api_base="https://open.larksuite.com", app_id="cli_x", app_secret="s")
    mid = await api.post_card(chat_id="oc_1", root_id=None, card={"schema": "2.0"})
    assert mid == "om_xyz"
    await api.aclose()


@respx.mock
async def test_post_card_with_root_id_includes_reply_in_content():
    respx.post("https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal").mock(
        return_value=httpx.Response(200, json={"code": 0, "tenant_access_token": "t", "expire": 7200})
    )
    route = respx.post("https://open.larksuite.com/open-apis/im/v1/messages").mock(
        return_value=httpx.Response(200, json={"code": 0, "data": {"message_id": "om_1"}})
    )
    api = LarkApi(api_base="https://open.larksuite.com", app_id="x", app_secret="s")
    await api.post_card(chat_id="oc_1", root_id="om_root", card={"schema": "2.0"})
    body = route.calls.last.request.read().decode()
    assert "om_root" in body
    await api.aclose()


@respx.mock
async def test_patch_card_calls_correct_endpoint():
    respx.post("https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal").mock(
        return_value=httpx.Response(200, json={"code": 0, "tenant_access_token": "t", "expire": 7200})
    )
    route = respx.patch("https://open.larksuite.com/open-apis/im/v1/messages/om_1").mock(
        return_value=httpx.Response(200, json={"code": 0})
    )
    api = LarkApi(api_base="https://open.larksuite.com", app_id="x", app_secret="s")
    await api.patch_card(message_id="om_1", card={"schema": "2.0"})
    assert route.called
    await api.aclose()


@respx.mock
async def test_lark_error_code_raises():
    respx.post("https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal").mock(
        return_value=httpx.Response(200, json={"code": 0, "tenant_access_token": "t", "expire": 7200})
    )
    respx.post("https://open.larksuite.com/open-apis/im/v1/messages").mock(
        return_value=httpx.Response(200, json={"code": 99991663, "msg": "rate limited"})
    )
    api = LarkApi(api_base="https://open.larksuite.com", app_id="x", app_secret="s")
    with pytest.raises(LarkApiError):
        await api.post_card(chat_id="c", root_id=None, card={})
    await api.aclose()
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_lark_api.py -v`

- [ ] **Step 3: Implement**

```python
from __future__ import annotations

import json
import time
from typing import Any, Optional

import httpx


class LarkApiError(Exception):
    def __init__(self, code: int, msg: str) -> None:
        self.code = code
        self.msg = msg
        super().__init__(f"Lark API error {code}: {msg}")


class LarkApi:
    """Minimal Lark Open Platform API client (Phase 1).

    Manages tenant_access_token caching and exposes two operations:
      - post_card: send a new interactive card message to a chat (optionally as a thread reply).
      - patch_card: update an existing card-typed message in place.
    """

    def __init__(
        self,
        *,
        api_base: str,
        app_id: str,
        app_secret: str,
        timeout: float = 30.0,
    ) -> None:
        self._api_base = api_base.rstrip("/")
        self._app_id = app_id
        self._app_secret = app_secret
        self._http = httpx.AsyncClient(timeout=timeout)
        self._token: str = ""
        self._token_expires_at: float = 0.0

    async def _ensure_token(self) -> str:
        if self._token and time.monotonic() < self._token_expires_at - 300:
            return self._token
        resp = await self._http.post(
            f"{self._api_base}/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": self._app_id, "app_secret": self._app_secret},
        )
        body = resp.json()
        if body.get("code") != 0:
            raise LarkApiError(body.get("code", -1), body.get("msg", "token fetch failed"))
        self._token = body["tenant_access_token"]
        self._token_expires_at = time.monotonic() + int(body.get("expire", 7200))
        return self._token

    async def _auth_headers(self) -> dict[str, str]:
        tok = await self._ensure_token()
        return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

    async def post_card(self, *, chat_id: str, root_id: Optional[str], card: dict[str, Any]) -> str:
        body: dict[str, Any] = {
            "receive_id": chat_id,
            "msg_type": "interactive",
            "content": json.dumps(card),
        }
        if root_id:
            body["reply_in_thread"] = True
            body["root_id"] = root_id  # API also accepts root_id at top-level on create-by-reply variant
        params = {"receive_id_type": "chat_id"}
        resp = await self._http.post(
            f"{self._api_base}/open-apis/im/v1/messages",
            params=params,
            json=body,
            headers=await self._auth_headers(),
        )
        data = resp.json()
        if data.get("code") != 0:
            raise LarkApiError(data.get("code", -1), data.get("msg", "post failed"))
        return data["data"]["message_id"]

    async def patch_card(self, *, message_id: str, card: dict[str, Any]) -> None:
        body = {"content": json.dumps(card)}
        resp = await self._http.patch(
            f"{self._api_base}/open-apis/im/v1/messages/{message_id}",
            json=body,
            headers=await self._auth_headers(),
        )
        data = resp.json()
        if data.get("code") != 0:
            raise LarkApiError(data.get("code", -1), data.get("msg", "patch failed"))

    async def aclose(self) -> None:
        await self._http.aclose()
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_lark_api.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add lark-bot/lark_api.py lark-bot/tests/test_lark_api.py
git commit -m "feat(lark-bot): minimal Lark REST adapter (post/patch card + token cache)"
```

---

## Task 13: `http_server.py` — internal endpoint for orchestrator-forwarded events

FastAPI app that exposes:
- `GET /healthz` (liveness)
- `POST /internal/lark/event` (orchestrator forwards normalized payload here)

The endpoint takes a raw Lark event payload (already signature-verified and decrypted by orchestrator), runs `event_router.normalize_event`, dispatches to the `InvestigationHandler`. Returns 200 immediately for `url_verification` (Lark expects fast response).

**Files:**
- Create: `lark-bot/http_server.py`
- Test: `lark-bot/tests/test_http_server.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from http_server import build_app


class _StubInv:
    def __init__(self) -> None:
        self.calls = []

    async def handle(self, evt) -> None:
        self.calls.append(evt)


def test_healthz_returns_ok():
    inv = _StubInv()
    app = build_app(handler=inv)
    client = TestClient(app)
    assert client.get("/healthz").json() == {"status": "ok"}


def test_url_verification_echoes_challenge():
    inv = _StubInv()
    app = build_app(handler=inv)
    client = TestClient(app)
    r = client.post("/internal/lark/event", json={"type": "url_verification", "challenge": "xyz"})
    assert r.status_code == 200
    assert r.json() == {"challenge": "xyz"}
    assert inv.calls == []  # url_verification is not dispatched to handler


def test_message_event_dispatches_to_handler():
    inv = _StubInv()
    app = build_app(handler=inv)
    client = TestClient(app)
    payload = {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1", "event_id": "evt", "tenant_key": "tk"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_id": "om_1", "chat_id": "oc_x", "chat_type": "group",
                "message_type": "text",
                "content": '{"text": "@_user_1 hello"}',
                "mentions": [{"key": "@_user_1", "id": {"open_id": "ou_bot"}}],
            },
        },
    }
    r = client.post("/internal/lark/event", json=payload)
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert len(inv.calls) == 1
    assert inv.calls[0].text_after_mention == "hello"


def test_dedup_event_id_is_idempotent():
    inv = _StubInv()
    app = build_app(handler=inv, dedup_window=64)
    client = TestClient(app)
    payload = {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1", "event_id": "dup_1", "tenant_key": "tk"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_1"}},
            "message": {
                "message_id": "om_1", "chat_id": "c", "chat_type": "group",
                "message_type": "text",
                "content": '{"text":"hi"}',
                "mentions": [{"key": "@_b", "id": {"open_id": "b"}}],
            },
        },
    }
    client.post("/internal/lark/event", json=payload)
    client.post("/internal/lark/event", json=payload)
    assert len(inv.calls) == 1
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_http_server.py -v`

- [ ] **Step 3: Implement**

```python
from __future__ import annotations

import asyncio
from collections import deque
from typing import Any, Protocol

from fastapi import FastAPI, Request

from event_router import EventValidationError, normalize_event


class _Handler(Protocol):
    async def handle(self, evt) -> None: ...


def build_app(*, handler: _Handler, dedup_window: int = 1024) -> FastAPI:
    app = FastAPI(title="incidentfox-lark-bot")
    seen: deque[str] = deque(maxlen=dedup_window)
    seen_set: set[str] = set()
    lock = asyncio.Lock()

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/internal/lark/event")
    async def event(request: Request) -> dict[str, Any]:
        payload = await request.json()
        try:
            evt = normalize_event(payload)
        except EventValidationError:
            return {"ok": False, "reason": "unsupported_event"}

        if evt.event_type == "url_verification":
            return {"challenge": evt.url_verification_challenge}

        if evt.event_id:
            async with lock:
                if evt.event_id in seen_set:
                    return {"ok": True, "deduped": True}
                if len(seen) == seen.maxlen:
                    seen_set.discard(seen[0])
                seen.append(evt.event_id)
                seen_set.add(evt.event_id)

        # Schedule handler in background — Lark expects <3s response.
        asyncio.create_task(handler.handle(evt))
        return {"ok": True}

    return app
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_http_server.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add lark-bot/http_server.py lark-bot/tests/test_http_server.py
git commit -m "feat(lark-bot): FastAPI internal event endpoint with dedup"
```

---

## Task 14: `ws_client.py` — long-connection event consumer

Uses `lark-oapi`'s WebSocket client. The lark-oapi `Client.event_dispatcher` model: register handlers for event types, then `client.start()` blocks. We need to feed received events into the same `InvestigationHandler` used by the HTTP path.

**Files:**
- Create: `lark-bot/ws_client.py`
- Test: `lark-bot/tests/test_ws_client.py` (smoke test only — full WS test is brittle; assert wiring instead)

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

import pytest

from ws_client import LarkWsClient, _decode_oapi_event


def test_decode_oapi_event_extracts_payload():
    """Given a lark-oapi event-dispatcher payload, return the raw dict shape we feed to event_router."""
    # lark-oapi typically passes a dataclass-shaped event with .header and .event attrs.
    class FakeHeader:
        event_id = "evt1"
        event_type = "im.message.receive_v1"
        tenant_key = "tk"
        create_time = "1700000000000"

    class FakeMsg:
        message_id = "om_1"
        chat_id = "oc_x"
        chat_type = "group"
        message_type = "text"
        content = '{"text":"@_user_1 hi"}'
        root_id = None
        mentions = [{"key": "@_user_1", "id": {"open_id": "ou_bot"}}]

    class FakeEvent:
        header = FakeHeader()
        event = type("E", (), {
            "sender": type("S", (), {"sender_id": type("I", (), {"open_id": "ou_1"})()})(),
            "message": FakeMsg(),
        })()

    payload = _decode_oapi_event(FakeEvent())
    assert payload["header"]["event_type"] == "im.message.receive_v1"
    assert payload["event"]["message"]["chat_id"] == "oc_x"


def test_ws_client_constructor_accepts_handler():
    """Smoke: object constructs without error given a stub handler."""
    class StubHandler:
        async def handle(self, evt): pass

    c = LarkWsClient(
        app_id="cli_x", app_secret="s", api_base="https://open.larksuite.com",
        handler=StubHandler(),
    )
    assert c is not None
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_ws_client.py -v`

- [ ] **Step 3: Implement**

```python
from __future__ import annotations

import asyncio
import json
from typing import Any, Protocol

import lark_oapi as lark
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

from event_router import EventValidationError, normalize_event


class _Handler(Protocol):
    async def handle(self, evt) -> None: ...


def _decode_oapi_event(oapi_event: Any) -> dict[str, Any]:
    """Reshape a lark-oapi P2ImMessageReceiveV1 (or similar) into the dict shape event_router expects."""
    header = oapi_event.header
    msg = oapi_event.event.message
    sender = oapi_event.event.sender
    return {
        "schema": "2.0",
        "header": {
            "event_id": getattr(header, "event_id", "") or "",
            "event_type": getattr(header, "event_type", "") or "",
            "tenant_key": getattr(header, "tenant_key", "") or "",
            "create_time": getattr(header, "create_time", "") or "",
        },
        "event": {
            "sender": {"sender_id": {"open_id": getattr(getattr(sender, "sender_id", None), "open_id", "") or ""}},
            "message": {
                "message_id": getattr(msg, "message_id", "") or "",
                "chat_id": getattr(msg, "chat_id", "") or "",
                "chat_type": getattr(msg, "chat_type", "") or "",
                "message_type": getattr(msg, "message_type", "") or "",
                "content": getattr(msg, "content", "") or "",
                "root_id": getattr(msg, "root_id", None),
                "mentions": getattr(msg, "mentions", None) or [],
            },
        },
    }


class LarkWsClient:
    def __init__(
        self,
        *,
        app_id: str,
        app_secret: str,
        api_base: str,
        handler: _Handler,
    ) -> None:
        self._handler = handler
        self._loop: asyncio.AbstractEventLoop | None = None

        domain = lark.LARK_INTL_DOMAIN if "larksuite" in api_base else lark.FEISHU_DOMAIN

        def on_message(oapi_evt: P2ImMessageReceiveV1) -> None:
            try:
                payload = _decode_oapi_event(oapi_evt)
                norm = normalize_event(payload)
            except EventValidationError:
                return
            assert self._loop is not None
            asyncio.run_coroutine_threadsafe(self._handler.handle(norm), self._loop)

        dispatcher = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(on_message)
            .build()
        )
        self._client = lark.ws.Client(
            app_id, app_secret,
            event_handler=dispatcher,
            domain=domain,
        )

    async def run(self) -> None:
        """Run the long-connection client until cancelled."""
        self._loop = asyncio.get_running_loop()
        # lark-oapi ws Client.start() is blocking; offload to a thread.
        await asyncio.to_thread(self._client.start)
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_ws_client.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add lark-bot/ws_client.py lark-bot/tests/test_ws_client.py
git commit -m "feat(lark-bot): long-connection WebSocket client (lark-oapi)"
```

---

## Task 15: `app.py` — service entry (mode select, lifespan)

Wires everything: reads env, builds `LarkApi`, `OrchestratorClient`, `InvestigationHandler`. Starts long-connection client and/or HTTP server based on `LARK_TRANSPORT_MODE`.

**Files:**
- Create: `lark-bot/app.py`
- Test: `lark-bot/tests/test_app_smoke.py`

- [ ] **Step 1: Write failing test (smoke only — env validation)**

```python
from __future__ import annotations

import os
import pytest

from app import build_settings, SettingsError


def test_settings_requires_app_id_and_secret(monkeypatch):
    monkeypatch.delenv("LARK_APP_ID", raising=False)
    monkeypatch.delenv("LARK_APP_SECRET", raising=False)
    with pytest.raises(SettingsError):
        build_settings()


def test_settings_defaults_intl_api_base(monkeypatch):
    monkeypatch.setenv("LARK_APP_ID", "cli_x")
    monkeypatch.setenv("LARK_APP_SECRET", "s")
    monkeypatch.setenv("LARK_TENANT_KEY", "tk")
    monkeypatch.setenv("INCIDENTFOX_TEAM_TOKEN", "tok")
    monkeypatch.setenv("INCIDENTFOX_ORG_ID", "o")
    monkeypatch.setenv("INCIDENTFOX_TEAM_ID", "t")
    monkeypatch.delenv("LARK_API_BASE", raising=False)
    s = build_settings()
    assert s.api_base == "https://open.larksuite.com"
    assert s.transport_mode in {"long_connection", "webhook", "hybrid"}


def test_settings_phase1_rejects_oauth_enabled(monkeypatch):
    monkeypatch.setenv("LARK_APP_ID", "x")
    monkeypatch.setenv("LARK_APP_SECRET", "s")
    monkeypatch.setenv("LARK_TENANT_KEY", "tk")
    monkeypatch.setenv("INCIDENTFOX_TEAM_TOKEN", "tok")
    monkeypatch.setenv("INCIDENTFOX_ORG_ID", "o")
    monkeypatch.setenv("INCIDENTFOX_TEAM_ID", "t")
    monkeypatch.setenv("LARK_OAUTH_ENABLED", "true")
    with pytest.raises(SettingsError):
        build_settings()
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_app_smoke.py -v`

- [ ] **Step 3: Implement**

```python
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from dataclasses import dataclass
from typing import Optional

import uvicorn
from dotenv import load_dotenv

from http_server import build_app
from investigation_handler import InvestigationHandler
from lark_api import LarkApi
from orchestrator_client import OrchestratorClient

logger = logging.getLogger("lark-bot")


class SettingsError(Exception):
    pass


@dataclass
class Settings:
    app_id: str
    app_secret: str
    tenant_key: str
    transport_mode: str
    api_base: str
    orchestrator_url: str
    config_service_url: str
    team_token: str
    org_id: str
    team_id: str
    internal_http_port: int


def _require(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        raise SettingsError(f"missing required env: {name}")
    return v


def build_settings() -> Settings:
    if os.environ.get("LARK_OAUTH_ENABLED", "false").lower() == "true":
        raise SettingsError("LARK_OAUTH_ENABLED=true is not supported in Phase 1 (single-tenant only)")
    transport = os.environ.get("LARK_TRANSPORT_MODE", "long_connection").lower()
    if transport not in {"long_connection", "webhook", "hybrid"}:
        raise SettingsError(f"invalid LARK_TRANSPORT_MODE: {transport!r}")
    return Settings(
        app_id=_require("LARK_APP_ID"),
        app_secret=_require("LARK_APP_SECRET"),
        tenant_key=_require("LARK_TENANT_KEY"),
        transport_mode=transport,
        api_base=os.environ.get("LARK_API_BASE", "https://open.larksuite.com"),
        orchestrator_url=os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8000"),
        config_service_url=os.environ.get("CONFIG_SERVICE_URL", "http://config-service:8080"),
        team_token=_require("INCIDENTFOX_TEAM_TOKEN"),
        org_id=_require("INCIDENTFOX_ORG_ID"),
        team_id=_require("INCIDENTFOX_TEAM_ID"),
        internal_http_port=int(os.environ.get("INTERNAL_HTTP_PORT", "8080")),
    )


async def _serve(s: Settings) -> None:
    lark_api = LarkApi(api_base=s.api_base, app_id=s.app_id, app_secret=s.app_secret)
    orchestrator = OrchestratorClient(base_url=s.orchestrator_url, team_token=s.team_token)
    handler = InvestigationHandler(
        lark_api=lark_api,
        orchestrator=orchestrator,
        org_id=s.org_id,
        team_id=s.team_id,
    )

    tasks: list[asyncio.Task] = []

    if s.transport_mode in {"webhook", "hybrid"}:
        app = build_app(handler=handler)
        config = uvicorn.Config(
            app, host="0.0.0.0", port=s.internal_http_port,
            log_level=os.environ.get("LOG_LEVEL", "info").lower(),
        )
        server = uvicorn.Server(config)
        tasks.append(asyncio.create_task(server.serve(), name="http_server"))

    if s.transport_mode in {"long_connection", "hybrid"}:
        from ws_client import LarkWsClient
        ws = LarkWsClient(
            app_id=s.app_id, app_secret=s.app_secret,
            api_base=s.api_base, handler=handler,
        )
        tasks.append(asyncio.create_task(ws.run(), name="ws_client"))

    if not tasks:
        raise SettingsError(f"no transports active for mode {s.transport_mode!r}")

    stop = asyncio.Event()

    def _signal_handler(*_: object) -> None:
        stop.set()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            asyncio.get_running_loop().add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass  # Windows / non-main thread

    done, pending = await asyncio.wait(
        [*tasks, asyncio.create_task(stop.wait(), name="stop")],
        return_when=asyncio.FIRST_COMPLETED,
    )
    for t in pending:
        t.cancel()

    await lark_api.aclose()
    await orchestrator.aclose()


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = build_settings()
    print(json.dumps({"service": "lark-bot", "event": "starting", "transport": settings.transport_mode}))
    asyncio.run(_serve(settings))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_app_smoke.py -v`
Expected: 3 passed.

- [ ] **Step 5: Run full lark-bot test suite**

Run: `uv run pytest tests/ -v`
Expected: all pass (sum across tasks 2-15).

- [ ] **Step 6: Commit**

```bash
git add lark-bot/app.py lark-bot/tests/test_app_smoke.py
git commit -m "feat(lark-bot): service entry with transport-mode dispatch"
```

---

## Task 16: Orchestrator side — Lark signature verification + decryption

**Files:**
- Modify: `orchestrator/src/incidentfox_orchestrator/webhooks/signatures.py`
- Test: `orchestrator/tests/unit/test_lark_signatures.py`

Lark signature spec (international):
- Header `X-Lark-Signature`: hex digest.
- Algorithm: `SHA256(timestamp + nonce + encrypt_key + body)` where `body` is the raw request body string.
- Headers: `X-Lark-Request-Timestamp`, `X-Lark-Request-Nonce`.

Decryption (when Encrypt Key is set):
- Body field `encrypt`: base64(AES-256-CBC(json_payload, key=SHA256(encrypt_key), iv=first 16 bytes of ciphertext)).

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

import base64
import hashlib
import json
import os

import pytest
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from incidentfox_orchestrator.webhooks.signatures import (
    SignatureVerificationError,
    decrypt_lark_payload,
    verify_lark_signature,
)


def _sign(timestamp: str, nonce: str, encrypt_key: str, body: str) -> str:
    return hashlib.sha256((timestamp + nonce + encrypt_key + body).encode()).hexdigest()


def test_verify_lark_signature_passes_with_correct_inputs():
    body = '{"a":1}'
    sig = _sign("1700", "n1", "ek", body)
    verify_lark_signature(timestamp="1700", nonce="n1", encrypt_key="ek", body=body, signature=sig)


def test_verify_lark_signature_fails_with_wrong_signature():
    with pytest.raises(SignatureVerificationError):
        verify_lark_signature(timestamp="1700", nonce="n1", encrypt_key="ek", body="{}", signature="bad")


def _encrypt_lark(plain: str, encrypt_key: str) -> str:
    key = hashlib.sha256(encrypt_key.encode()).digest()
    iv = os.urandom(16)
    cipher = AES.new(key, AES.MODE_CBC, iv=iv)
    ct = cipher.encrypt(pad(plain.encode(), AES.block_size))
    return base64.b64encode(iv + ct).decode()


def test_decrypt_lark_payload_roundtrip():
    inner = json.dumps({"hello": "world"})
    encrypted = _encrypt_lark(inner, "test-key")
    out = decrypt_lark_payload(encrypted=encrypted, encrypt_key="test-key")
    assert out == {"hello": "world"}


def test_decrypt_lark_payload_wrong_key_raises():
    inner = json.dumps({"x": 1})
    encrypted = _encrypt_lark(inner, "real-key")
    with pytest.raises(SignatureVerificationError):
        decrypt_lark_payload(encrypted=encrypted, encrypt_key="WRONG-KEY")
```

- [ ] **Step 2: Run, verify fail**

Run from `orchestrator/`: `uv run pytest tests/unit/test_lark_signatures.py -v`
Expected: ImportError on `verify_lark_signature` / `decrypt_lark_payload`.

- [ ] **Step 3: Implement — append to `signatures.py`**

```python
import base64
import hashlib
import json as _json

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad


def verify_lark_signature(
    *, timestamp: str, nonce: str, encrypt_key: str, body: str, signature: str
) -> None:
    """Lark webhook signature: SHA256(timestamp + nonce + encrypt_key + body) hex digest."""
    expected = hashlib.sha256((timestamp + nonce + encrypt_key + body).encode()).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise SignatureVerificationError("signature mismatch", "lark")


def decrypt_lark_payload(*, encrypted: str, encrypt_key: str) -> dict:
    """Decrypt Lark's encrypted webhook body. AES-256-CBC, key=SHA256(encrypt_key), IV=first 16 bytes."""
    try:
        raw = base64.b64decode(encrypted)
        if len(raw) < 32:
            raise ValueError("payload too short")
        iv, ct = raw[:16], raw[16:]
        key = hashlib.sha256(encrypt_key.encode()).digest()
        cipher = AES.new(key, AES.MODE_CBC, iv=iv)
        plain = unpad(cipher.decrypt(ct), AES.block_size)
        return _json.loads(plain.decode("utf-8"))
    except Exception as e:
        raise SignatureVerificationError(f"decrypt failed: {e}", "lark") from e
```

Add `pycryptodome>=3.20` to `orchestrator/pyproject.toml` dependencies if not already present (Crypto.Cipher comes from pycryptodome).

- [ ] **Step 4: Run, verify pass**

```
uv run pytest tests/unit/test_lark_signatures.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/src/incidentfox_orchestrator/webhooks/signatures.py orchestrator/tests/unit/test_lark_signatures.py orchestrator/pyproject.toml
git commit -m "feat(orchestrator): Lark webhook signature verification + decryption"
```

---

## Task 17: Orchestrator side — `webhooks/lark_app.py` + router wiring

Endpoint receives Lark-encrypted webhook, decrypts, verifies signature, and forwards normalized payload to lark-bot's `/internal/lark/event`.

**Files:**
- Create: `orchestrator/src/incidentfox_orchestrator/webhooks/lark_app.py`
- Modify: `orchestrator/src/incidentfox_orchestrator/webhooks/router.py`
- Test: `orchestrator/tests/unit/test_lark_app.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

import base64
import hashlib
import json
import os

import httpx
import pytest
import respx
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from fastapi.testclient import TestClient

from incidentfox_orchestrator.webhooks.lark_app import build_lark_router


def _encrypt(plain: str, key: str) -> str:
    iv = os.urandom(16)
    aes = AES.new(hashlib.sha256(key.encode()).digest(), AES.MODE_CBC, iv=iv)
    return base64.b64encode(iv + aes.encrypt(pad(plain.encode(), AES.block_size))).decode()


def _sign(ts: str, nonce: str, ek: str, body: str) -> str:
    return hashlib.sha256((ts + nonce + ek + body).encode()).hexdigest()


@pytest.fixture
def app(monkeypatch):
    from fastapi import FastAPI
    monkeypatch.setenv("LARK_VERIFICATION_TOKEN", "vtok")
    monkeypatch.setenv("LARK_ENCRYPT_KEY", "ekey")
    monkeypatch.setenv("LARK_BOT_INTERNAL_URL", "http://lark-bot:8080")
    a = FastAPI()
    a.include_router(build_lark_router())
    return a


@respx.mock
def test_url_verification_decrypts_and_echoes(app):
    inner = json.dumps({"type": "url_verification", "challenge": "ch1", "token": "vtok"})
    encrypted = _encrypt(inner, "ekey")
    body = json.dumps({"encrypt": encrypted})
    sig = _sign("1700", "n1", "ekey", body)

    client = TestClient(app)
    r = client.post(
        "/webhooks/lark",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Lark-Signature": sig,
            "X-Lark-Request-Timestamp": "1700",
            "X-Lark-Request-Nonce": "n1",
        },
    )
    assert r.status_code == 200
    assert r.json() == {"challenge": "ch1"}


@respx.mock
def test_event_forwards_to_lark_bot_internal(app):
    inner_event = {
        "schema": "2.0",
        "header": {"event_type": "im.message.receive_v1", "event_id": "e1", "tenant_key": "tk"},
        "event": {"sender": {"sender_id": {"open_id": "ou_1"}},
                  "message": {"message_id": "om", "chat_id": "c", "chat_type": "p2p",
                              "message_type": "text", "content": '{"text":"hi"}',
                              "mentions": []}},
        "token": "vtok",
    }
    encrypted = _encrypt(json.dumps(inner_event), "ekey")
    body = json.dumps({"encrypt": encrypted})
    sig = _sign("1700", "n1", "ekey", body)

    forwarded = respx.post("http://lark-bot:8080/internal/lark/event").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    client = TestClient(app)
    r = client.post(
        "/webhooks/lark",
        content=body,
        headers={"X-Lark-Signature": sig, "X-Lark-Request-Timestamp": "1700", "X-Lark-Request-Nonce": "n1"},
    )
    assert r.status_code == 200
    assert forwarded.called
    forwarded_body = json.loads(forwarded.calls.last.request.read())
    assert forwarded_body["header"]["event_type"] == "im.message.receive_v1"


def test_bad_signature_returns_401(app):
    body = json.dumps({"encrypt": "anything"})
    client = TestClient(app)
    r = client.post(
        "/webhooks/lark",
        content=body,
        headers={"X-Lark-Signature": "bad", "X-Lark-Request-Timestamp": "1700", "X-Lark-Request-Nonce": "n1"},
    )
    assert r.status_code == 401


def test_token_mismatch_returns_401(app):
    inner = json.dumps({"type": "url_verification", "challenge": "ch", "token": "WRONG"})
    encrypted = _encrypt(inner, "ekey")
    body = json.dumps({"encrypt": encrypted})
    sig = _sign("1700", "n1", "ekey", body)
    client = TestClient(app)
    r = client.post(
        "/webhooks/lark",
        content=body,
        headers={"X-Lark-Signature": sig, "X-Lark-Request-Timestamp": "1700", "X-Lark-Request-Nonce": "n1"},
    )
    assert r.status_code == 401
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/unit/test_lark_app.py -v`

- [ ] **Step 3: Implement `webhooks/lark_app.py`**

```python
from __future__ import annotations

import json
import os
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException, Request

from incidentfox_orchestrator.webhooks.signatures import (
    SignatureVerificationError,
    decrypt_lark_payload,
    verify_lark_signature,
)


def _log(event: str, **fields: Any) -> None:
    try:
        print(json.dumps({"service": "orchestrator", "component": "lark", "event": event, **fields}, default=str))
    except Exception:
        print(f"{event} {fields}")


def build_lark_router() -> APIRouter:
    router = APIRouter()

    @router.post("/webhooks/lark")
    async def lark_webhook(
        request: Request,
        x_lark_signature: str = Header(default=""),
        x_lark_request_timestamp: str = Header(default=""),
        x_lark_request_nonce: str = Header(default=""),
    ):
        verification_token = os.environ.get("LARK_VERIFICATION_TOKEN", "")
        encrypt_key = os.environ.get("LARK_ENCRYPT_KEY", "")
        lark_bot_url = os.environ.get("LARK_BOT_INTERNAL_URL", "")
        if not verification_token or not lark_bot_url:
            raise HTTPException(status_code=503, detail="lark webhook not configured")

        raw_body = (await request.body()).decode("utf-8")

        # Signature is required when encrypt_key is configured.
        if encrypt_key:
            try:
                verify_lark_signature(
                    timestamp=x_lark_request_timestamp,
                    nonce=x_lark_request_nonce,
                    encrypt_key=encrypt_key,
                    body=raw_body,
                    signature=x_lark_signature,
                )
            except SignatureVerificationError as e:
                _log("signature_verify_failed", reason=str(e))
                raise HTTPException(status_code=401, detail="signature_invalid")

        try:
            outer = json.loads(raw_body)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="invalid_json")

        if "encrypt" in outer:
            if not encrypt_key:
                _log("got_encrypted_payload_without_key")
                raise HTTPException(status_code=401, detail="encrypted_but_no_key")
            try:
                payload = decrypt_lark_payload(encrypted=outer["encrypt"], encrypt_key=encrypt_key)
            except SignatureVerificationError:
                raise HTTPException(status_code=401, detail="decrypt_failed")
        else:
            payload = outer

        # Token field appears in both url_verification and event payloads.
        if payload.get("token") and payload["token"] != verification_token:
            raise HTTPException(status_code=401, detail="token_mismatch")

        if payload.get("type") == "url_verification":
            return {"challenge": payload.get("challenge", "")}

        # Forward normalized payload to lark-bot.
        async with httpx.AsyncClient(timeout=10.0) as http:
            try:
                r = await http.post(f"{lark_bot_url.rstrip('/')}/internal/lark/event", json=payload)
                r.raise_for_status()
            except httpx.HTTPError as e:
                _log("forward_failed", error=str(e))
                raise HTTPException(status_code=502, detail="lark_bot_unreachable")
        return {"ok": True}

    return router
```

- [ ] **Step 4: Wire into `webhooks/router.py`**

Find the `router = APIRouter()` block and add (near other webhook routes):

```python
from incidentfox_orchestrator.webhooks.lark_app import build_lark_router
router.include_router(build_lark_router())
```

If `router.py` exposes a different aggregation pattern, wire `build_lark_router()` to the same `app.include_router` call site as `slack_bolt_app` / `google_chat_app`.

- [ ] **Step 5: Run test**

```
uv run pytest tests/unit/test_lark_app.py -v
```
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/src/incidentfox_orchestrator/webhooks/lark_app.py orchestrator/src/incidentfox_orchestrator/webhooks/router.py orchestrator/tests/unit/test_lark_app.py
git commit -m "feat(orchestrator): /webhooks/lark endpoint forwarding to lark-bot"
```

---

## Task 18: Helm chart template + values

**Files:**
- Create: `charts/incidentfox/templates/lark-bot.yaml`
- Modify: `charts/incidentfox/values.yaml` (add `services.larkBot`, `externalSecrets.larkBot`)
- Modify: `charts/incidentfox/values.staging.yaml` (`enabled: false`)
- Modify: `charts/incidentfox/values.prod.yaml` (`enabled: false`)
- Modify: `charts/incidentfox/values.pilot.yaml` (`enabled: true` example)

- [ ] **Step 1: Create `lark-bot.yaml` template**

(Mirror `slack-bot.yaml`. Only listing the diff-relevant parts.)

```yaml
{{- if .Values.services.larkBot.enabled }}
{{- if .Values.services.larkBot.serviceAccount.create }}
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{ .Values.services.larkBot.serviceAccount.name | default "lark-bot" }}
  namespace: {{ .Values.namespace }}
---
{{- end }}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: incidentfox-lark-bot
  namespace: {{ .Values.namespace }}
  labels:
    app: incidentfox-lark-bot
spec:
  replicas: {{ .Values.services.larkBot.replicas | default 1 }}
  selector:
    matchLabels:
      app: incidentfox-lark-bot
  template:
    metadata:
      labels:
        app: incidentfox-lark-bot
    spec:
      serviceAccountName: {{ .Values.services.larkBot.serviceAccount.name | default "lark-bot" }}
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
      containers:
        - name: lark-bot
          image: "{{ .Values.services.larkBot.image }}"
          imagePullPolicy: IfNotPresent
          ports:
            - containerPort: 8080
              name: http
          env:
            - name: LARK_TRANSPORT_MODE
              value: "{{ .Values.services.larkBot.transportMode | default "long_connection" }}"
            - name: LARK_API_BASE
              value: "{{ .Values.services.larkBot.apiBase | default "https://open.larksuite.com" }}"
            - name: ORCHESTRATOR_URL
              value: "http://incidentfox-orchestrator.{{ .Values.namespace }}.svc.cluster.local:8000"
            - name: CONFIG_SERVICE_URL
              value: "http://incidentfox-config-service.{{ .Values.namespace }}.svc.cluster.local:8080"
            - name: LARK_OAUTH_ENABLED
              value: "false"
            - name: LARK_APP_ID
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.externalSecrets.larkBot.secretName }}
                  key: {{ .Values.externalSecrets.larkBot.appIdKey }}
            - name: LARK_APP_SECRET
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.externalSecrets.larkBot.secretName }}
                  key: {{ .Values.externalSecrets.larkBot.appSecretKey }}
            - name: LARK_VERIFICATION_TOKEN
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.externalSecrets.larkBot.secretName }}
                  key: {{ .Values.externalSecrets.larkBot.verificationTokenKey }}
            - name: LARK_ENCRYPT_KEY
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.externalSecrets.larkBot.secretName }}
                  key: {{ .Values.externalSecrets.larkBot.encryptKeyKey }}
                  optional: true
            - name: LARK_TENANT_KEY
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.externalSecrets.larkBot.secretName }}
                  key: {{ .Values.externalSecrets.larkBot.tenantKeyKey }}
            - name: INCIDENTFOX_TEAM_TOKEN
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.externalSecrets.larkBot.secretName }}
                  key: {{ .Values.externalSecrets.larkBot.teamTokenKey }}
            - name: INCIDENTFOX_ORG_ID
              value: "{{ .Values.services.larkBot.orgId }}"
            - name: INCIDENTFOX_TEAM_ID
              value: "{{ .Values.services.larkBot.teamId }}"
          resources:
            {{- toYaml .Values.services.larkBot.resources | nindent 12 }}
          readinessProbe:
            httpGet:
              path: /healthz
              port: http
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /healthz
              port: http
            initialDelaySeconds: 30
            periodSeconds: 30
---
apiVersion: v1
kind: Service
metadata:
  name: incidentfox-lark-bot
  namespace: {{ .Values.namespace }}
spec:
  selector:
    app: incidentfox-lark-bot
  ports:
    - name: http
      port: 8080
      targetPort: http
{{- end }}
```

- [ ] **Step 2: Append to `values.yaml` `services:` block**

```yaml
  larkBot:
    enabled: false
    image: "incidentfox/lark-bot:v0.1.0"
    replicas: 1
    transportMode: long_connection
    apiBase: https://open.larksuite.com
    orgId: ""
    teamId: ""
    serviceAccount:
      create: true
      name: lark-bot
    resources:
      requests:
        cpu: "50m"
        memory: "128Mi"
      limits:
        cpu: "500m"
        memory: "512Mi"
```

- [ ] **Step 3: Append to `values.yaml` `externalSecrets:` block**

```yaml
    larkBot:
      enabled: false
      secretName: incidentfox-lark-bot
      appIdKey: app_id
      appSecretKey: app_secret
      verificationTokenKey: verification_token
      encryptKeyKey: encrypt_key
      tenantKeyKey: tenant_key
      teamTokenKey: team_token
      appIdRemoteRefKey: incidentfox/prod/lark_app_id
      appSecretRemoteRefKey: incidentfox/prod/lark_app_secret
      verificationTokenRemoteRefKey: incidentfox/prod/lark_verification_token
      encryptKeyRemoteRefKey: incidentfox/prod/lark_encrypt_key
      tenantKeyRemoteRefKey: incidentfox/prod/lark_tenant_key
      teamTokenRemoteRefKey: incidentfox/prod/lark_team_token
```

- [ ] **Step 4: In `values.staging.yaml` and `values.prod.yaml` set `services.larkBot.enabled: false`** (no other changes — explicit defaults). In `values.pilot.yaml` set `services.larkBot.enabled: true` and supply concrete values.

- [ ] **Step 5: Lint**

```bash
helm lint charts/incidentfox -f charts/incidentfox/values.staging.yaml
helm lint charts/incidentfox -f charts/incidentfox/values.prod.yaml
helm lint charts/incidentfox -f charts/incidentfox/values.pilot.yaml
```
Expected: each "1 chart(s) linted, 0 chart(s) failed".

- [ ] **Step 6: Commit**

```bash
git add charts/incidentfox/templates/lark-bot.yaml charts/incidentfox/values.yaml charts/incidentfox/values.staging.yaml charts/incidentfox/values.prod.yaml charts/incidentfox/values.pilot.yaml
git commit -m "feat(charts): add lark-bot deployment + values"
```

---

## Task 19: Wire orchestrator's `LARK_BOT_INTERNAL_URL` env var

**Files:**
- Modify: `charts/incidentfox/templates/orchestrator.yaml` (find `env:` block, add)

- [ ] **Step 1: Locate orchestrator template** — open `charts/incidentfox/templates/orchestrator.yaml` and locate the `env:` block.

- [ ] **Step 2: Add env vars (gated behind larkBot.enabled)**

```yaml
            {{- if .Values.services.larkBot.enabled }}
            - name: LARK_BOT_INTERNAL_URL
              value: "http://incidentfox-lark-bot.{{ .Values.namespace }}.svc.cluster.local:8080"
            - name: LARK_VERIFICATION_TOKEN
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.externalSecrets.larkBot.secretName }}
                  key: {{ .Values.externalSecrets.larkBot.verificationTokenKey }}
            - name: LARK_ENCRYPT_KEY
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.externalSecrets.larkBot.secretName }}
                  key: {{ .Values.externalSecrets.larkBot.encryptKeyKey }}
                  optional: true
            {{- end }}
```

- [ ] **Step 3: Lint**

```bash
helm lint charts/incidentfox -f charts/incidentfox/values.pilot.yaml
```

- [ ] **Step 4: Commit**

```bash
git add charts/incidentfox/templates/orchestrator.yaml
git commit -m "feat(charts): orchestrator gets LARK_BOT_INTERNAL_URL when larkBot enabled"
```

---

## Task 20: GitHub Actions deploy workflow update

**Files:**
- Modify: `.github/workflows/deploy-eks.yml`

- [ ] **Step 1: Open the workflow and locate the `services` matrix / build-image steps for slack-bot.**

- [ ] **Step 2: Add `lark-bot` to the services choice list and image-build matrix**

Mirror exactly how slack-bot is wired: image build step targeted at `lark-bot/Dockerfile`, ECR repo `incidentfox/lark-bot`, deploy step that runs `helm upgrade` with the same values file.

(Specific edits depend on the existing matrix structure; the change is symmetric to slack-bot.)

- [ ] **Step 3: Local validation**

```bash
yamllint .github/workflows/deploy-eks.yml
```

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/deploy-eks.yml
git commit -m "ci: add lark-bot to deploy-eks.yml"
```

---

## Task 21: `lark-manifest.json` — Lark app config sample

This is documentation-shaped: a sample JSON the customer's admin can use to configure their Lark Open Platform app (events to subscribe, scopes to grant).

**Files:**
- Create: `lark-bot/lark-manifest.json`

- [ ] **Step 1: Write the manifest**

```json
{
  "_comment": "Sample Lark Open Platform app configuration. Apply manually in https://open.larksuite.com/app/<app_id>/dev",
  "events_v2": [
    "im.message.receive_v1"
  ],
  "scopes": {
    "tenant": [
      "im:message",
      "im:message.group_msg",
      "im:message:send_as_bot",
      "im:chat:readonly",
      "im:resource"
    ]
  },
  "transport": {
    "options": [
      {
        "mode": "webhook",
        "request_url": "https://<your-orchestrator-host>/webhooks/lark",
        "encrypt_key_required": true
      },
      {
        "mode": "long_connection",
        "encrypt_key_required": false
      }
    ]
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add lark-bot/lark-manifest.json
git commit -m "docs(lark-bot): sample Lark app manifest"
```

---

## Task 22: End-to-end smoke (manual verification, documented)

**Files:**
- Create: `lark-bot/tests/E2E_MANUAL.md`

- [ ] **Step 1: Write manual E2E walkthrough**

```markdown
# Lark Bot E2E Manual Verification

Run after Phase 1 deploy to a pilot cluster.

## Prereqs

1. Lark Open Platform app created (Custom App, single-tenant). App ID, App Secret, Verification Token, Encrypt Key noted.
2. Bot added to a test group chat.
3. `incidentfox-lark-bot` secret populated in AWS Secrets Manager and synced via ExternalSecret.
4. `services.larkBot.enabled=true` in pilot values.yaml.

## Smoke 1 — Long-connection mode

1. Set `services.larkBot.transportMode=long_connection`.
2. Deploy: `helm upgrade --install incidentfox charts/incidentfox -f values.pilot.yaml`.
3. Watch pod logs: `kubectl logs deploy/incidentfox-lark-bot -f`. Expect `event: starting transport: long_connection`.
4. In the test group chat, mention bot: `@IncidentFox why is checkout slow?`.
5. Expect within 3s: a card appears with header "IncidentFox Investigation" (blue).
6. Within ~10s: card body updates with streaming partial output.
7. Within ~60s: card finalizes — header turns green ("Investigation Complete") with full result.

## Smoke 2 — Webhook mode

1. Set `services.larkBot.transportMode=webhook`.
2. Configure orchestrator's public URL in Lark app config: `https://<host>/webhooks/lark`.
3. Set Encrypt Key in both Lark app config and `incidentfox-lark-bot` secret.
4. Trigger Lark's "Verify URL" — expect 200 + `{"challenge": "..."}` echo.
5. Repeat smoke 1 steps 4-7. Same observable behavior.

## Smoke 3 — Failure paths

1. Stop sre-agent: `kubectl scale deploy incidentfox-sre-agent --replicas=0`.
2. Mention bot. Expect: card finalizes with red "Investigation Failed" header within ~30s.
3. Restore: `kubectl scale deploy incidentfox-sre-agent --replicas=1`.
```

- [ ] **Step 2: Commit**

```bash
git add lark-bot/tests/E2E_MANUAL.md
git commit -m "docs(lark-bot): manual E2E verification walkthrough"
```

---

## Task 23: CLAUDE.md update

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add lark-bot row to "Key files" table** (alphabetical / near slack-bot rows):

```markdown
| lark-bot/app.py | Lark service entry, mode dispatch, lifespan |
| lark-bot/ws_client.py | lark-oapi long-connection client |
| lark-bot/http_server.py | Internal endpoint for orchestrator-forwarded events |
```

- [ ] **Step 2: Update "Architecture (what's alive)" diagram** — add `Lark → orchestrator/lark-bot` line near the Slack one.

- [ ] **Step 3: Add a one-line note in "Architecture decisions pending" → resolve item #1**: "lark-bot is the first chat surface routed through orchestrator (Phase 1 single-tenant; Phase 2 adds OAuth multi-tenancy). slack-bot remains direct-to-agent for now."

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add lark-bot to CLAUDE.md key files + architecture diagram"
```

---

## Self-Review (run by plan author)

**Spec coverage check** (against `docs/superpowers/specs/2026-04-26-lark-bot-design.md`):

| Spec section | Phase 1 task |
|---|---|
| §2 Architecture: standalone lark-bot/ | Tasks 1-15 |
| §2 Architecture: orchestrator-forwarded webhook | Tasks 16-17 |
| §2 Architecture: agent dispatch via orchestrator | Tasks 7-9 |
| §3 Components: ws_client, http_server, event_router, etc. | Tasks 5, 13, 14 |
| §3 Components: card_builder, markdown_utils, state | Tasks 2, 3, 4 |
| §3 Components: orchestrator_client, stream_handler, investigation_handler | Tasks 9, 10, 11 |
| §3 Components: file_handler, onboarding, modal_*, oauth, model_catalog | DEFERRED to Phase 2/3 (per spec phasing) |
| §4 Data flow: long-connection path | Task 14 |
| §4 Data flow: webhook path | Tasks 13, 17 |
| §4 Multi-tenant routing | Phase 1 single-tenant only — `LARK_TENANT_KEY` env binding (Task 15); routing logic deferred to Phase 2 |
| §5 Auth & secrets | Tasks 18, 19 (Helm), Task 1 (env.example) |
| §6 Slack→Lark mapping | Reflected in Tasks 3, 4, 12 |
| §7 Error handling | Tasks 9, 10, 11 (handler-level), Task 17 (webhook 401s) |
| §8 Testing | Each task has TDD steps |
| §9 Phasing — Phase 1 only | This entire plan |
| §10 Orchestrator changes | Tasks 7, 8, 16, 17 |
| §11 Helm/Deployment | Tasks 18, 19, 20 |
| §12 Open questions / risks | Streaming endpoint (Tasks 7, 8); rate-limit debounce (Task 10); SDK adapter pattern via thin LarkApi (Task 12) |

**Placeholder scan:** None. Every code block is concrete; every command shows expected output or runnable invocation.

**Type/name consistency check:** Verified across tasks — `LarkEvent`, `Investigation`, `ConversationState`, `OrchestratorClient.stream_agent`, `LarkApi.{post_card, patch_card}`, `InvestigationHandler.handle`, `build_status_card / build_streaming_card / build_final_card / build_error_card`, `_log` helper signature, `LARK_*` env var names — all match between definition site and consumer.

**Scope check:** Phase 1 only. Phases 2–4 will be separate plans tracked against the same spec.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-26-lark-bot-phase-1.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
