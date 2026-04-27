# discord-bot Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Phase 1 of discord-bot — a standalone Python service that lets one Discord guild's users @-mention the bot in any channel, see a streaming agent investigation rendered as a progressively-edited rich embed, receive a final result, and react with 👍/👎 to record feedback.

**Architecture:** New standalone `discord-bot/` Python service. Connects to Discord Gateway via `discord.py` 2.x WebSocket. All agent dispatch routes through orchestrator's existing `/api/v1/agents/dispatch-stream` endpoint (added in lark-bot Phase 1) — no new orchestrator code needed. Single-guild only this phase: bot binds to `DISCORD_GUILD_ID` at boot.

**Tech Stack:** Python 3.11, `discord.py>=2.3` (Gateway client), `aiohttp` (small healthz server), `httpx` (orchestrator client + SSE), `pytest` + `pytest-asyncio` for tests, `uv` for deps. Helm chart matches existing lark-bot template structure.

**Spec reference:** `docs/superpowers/specs/2026-04-27-discord-bot-design.md` — Phase 1 of three-phase rollout.

**Reuses from lark-bot Phase 1:**
- Orchestrator's `POST /api/v1/agents/dispatch-stream` SSE-proxy endpoint — already shipped, no new orchestrator work needed.
- `OrchestratorClient` shape (copied verbatim with package rename).
- TDD patterns and project conventions.

---

## File Structure

**New service `discord-bot/`** (flat layout, mirroring lark-bot):

```
discord-bot/
  pyproject.toml
  Dockerfile
  README.md
  env.example
  .gitignore
  app.py                          # Service entry (env validation, lifecycle)
  gateway_client.py               # discord.py Bot wiring + on_message/on_reaction_add
  event_router.py                 # Normalize Discord events → unified shape
  embed_builder.py                # Discord rich-embed composition (status/streaming/final/error)
  markdown_utils.py               # Agent markdown → Discord markdown subset + 4000-char chunking
  state.py                        # In-memory bot_message_id → Investigation map
  orchestrator_client.py          # POST /api/v1/agents/dispatch-stream + SSE
  stream_handler.py               # SSE → debounced embed edits
  feedback_handler.py             # 👍/👎 reaction → config-service POST
  investigation_handler.py        # Lifecycle: post embed → stream → finalize → add reactions
  healthz.py                      # aiohttp /healthz endpoint for K8s probes
  tests/
    test_state.py
    test_markdown_utils.py
    test_embed_builder.py
    test_event_router.py
    test_orchestrator_client.py
    test_stream_handler.py
    test_feedback_handler.py
    test_investigation_handler.py
    test_app_smoke.py
```

**Helm chart additions:**

```
charts/incidentfox/
  templates/discord-bot.yaml      # NEW (mirror lark-bot.yaml)
  templates/external-secrets.yaml # MODIFY: + discordBot block
  templates/orchestrator.yaml     # NO CHANGES — orchestrator already supports lark-bot pattern
                                  # discord-bot uses orchestrator's existing dispatch-stream endpoint
  values.yaml                     # MODIFY: + services.discordBot, externalSecrets.contract.discordBot
  values.pilot.yaml               # MODIFY: example with services.discordBot.enabled=true
```

**Local dev:**

```
docker-compose.dev.yml            # MODIFY: + discord-bot service block
Makefile                          # MODIFY: + logs-discord target
.env.discord                      # NEW: env file template (gitignored)
```

**CI:**

```
.github/workflows/deploy-eks.yml  # MODIFY: + discord-bot to choices, build matrix, deploy steps
```

**Docs:**

```
CLAUDE.md                         # MODIFY: add discord-bot to architecture diagram + key files
docs/DISCORD_SETUP.md             # NEW: end-user setup guide (mirror LARK_SETUP.md)
discord-bot/README.md             # NEW: service-level dev README
```

---

## Conventions used throughout this plan

- **Python style:** ruff (project's existing config). Run `ruff check discord-bot/` before each commit.
- **Tests:** `pytest` from `discord-bot/` directory. `.venv/bin/python -m pytest tests/<file>::<test> -v`.
- **Type hints:** required on all public functions; `from __future__ import annotations` at top of every Python file.
- **Logging:** structured JSON via `_log(event, **fields)` helper (mirror orchestrator/lark-bot pattern).
- **Commits:** conventional commits format (`feat:`, `fix:`, `test:`, `chore:`).
- **Git author:** all commits use `-c user.name="ladung" -c user.email="ledung.is14@gmail.com"`.

---

## Task 1: Service scaffold (pyproject, Dockerfile, README, env.example)

**Files:**
- Create: `discord-bot/pyproject.toml`
- Create: `discord-bot/Dockerfile`
- Create: `discord-bot/README.md`
- Create: `discord-bot/env.example`
- Create: `discord-bot/.gitignore`

- [ ] **Step 1: Create `discord-bot/pyproject.toml`**

```toml
[project]
name = "incidentfox-discord-bot"
version = "0.1.0"
description = "Discord bot for IncidentFox AI SRE agent"
requires-python = ">=3.11"
dependencies = [
    "discord.py>=2.3.0",
    "aiohttp>=3.9.0",
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

- [ ] **Step 2: Create `discord-bot/Dockerfile`** (mirror lark-bot/Dockerfile pattern with the multi-source COPY fix)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml .
RUN uv pip install --system -e .

COPY *.py ./

RUN useradd -m -u 1000 discordbot && chown -R discordbot:discordbot /app
USER discordbot

EXPOSE 8080
CMD ["python", "app.py"]
```

- [ ] **Step 3: Create `discord-bot/env.example`**

```bash
# === Required ===
DISCORD_BOT_TOKEN=
DISCORD_APP_ID=
DISCORD_GUILD_ID=

# === Endpoints ===
ORCHESTRATOR_URL=http://orchestrator:8070
CONFIG_SERVICE_URL=http://config-service:8080
INTERNAL_HTTP_PORT=8080

# === IncidentFox identity ===
INCIDENTFOX_TEAM_TOKEN=
INCIDENTFOX_ORG_ID=
INCIDENTFOX_TEAM_ID=

# === Optional ===
LOG_LEVEL=INFO
```

- [ ] **Step 4: Create `discord-bot/.gitignore`**

```
__pycache__/
*.pyc
.venv/
venv/
.pytest_cache/
.ruff_cache/
.env
```

- [ ] **Step 5: Create `discord-bot/README.md`**

```markdown
# IncidentFox Discord Bot

Discord chat surface for IncidentFox AI SRE. Phase 1: single-guild, Gateway WebSocket connection, @mention trigger, streaming embed responses, 👍/👎 reaction feedback.

## Local dev

```
uv venv .venv
.venv/bin/uv pip install -e ".[dev]"
cp env.example .env  # fill in DISCORD_BOT_TOKEN, DISCORD_GUILD_ID, etc.
.venv/bin/python app.py
```

## Tests

```
.venv/bin/python -m pytest tests/ -v
```

See `docs/superpowers/specs/2026-04-27-discord-bot-design.md` for full design.
```

- [ ] **Step 6: Verify the scaffold installs**

```bash
cd /Users/anhdungle/data/SRE/ai-sre-agent-incidentfox/discord-bot
uv venv .venv
uv pip install --python .venv/bin/python -e ".[dev]"
```

Expected: clean install, no errors. discord.py 2.x and dev tools all installed.

- [ ] **Step 7: Commit**

```bash
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  add discord-bot/pyproject.toml discord-bot/Dockerfile discord-bot/README.md discord-bot/env.example discord-bot/.gitignore
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  commit -m "feat(discord-bot): scaffold service (pyproject, Dockerfile, env.example)"
```

---

## Task 2: `state.py` — in-memory conversation state

**Files:**
- Create: `discord-bot/state.py`
- Test: `discord-bot/tests/test_state.py`

- [ ] **Step 1: Write failing test `tests/test_state.py`**

```python
from __future__ import annotations

import re

from state import ConversationState, Investigation, generate_session_id


def test_session_id_stable_for_same_channel_and_message():
    a = generate_session_id(channel_id=12345, message_id=67890)
    b = generate_session_id(channel_id=12345, message_id=67890)
    assert a == b
    assert a.startswith("discord-")
    assert len(a) <= 63
    assert re.fullmatch(r"[a-z0-9-]+", a)


def test_session_id_handles_large_snowflake_ids():
    # Discord snowflake IDs are 18-19 digit integers
    sid = generate_session_id(channel_id=987654321098765432, message_id=123456789012345678)
    assert sid.startswith("discord-")
    assert len(sid) <= 63
    assert re.fullmatch(r"[a-z0-9-]+", sid)


def test_conversation_state_get_set():
    s = ConversationState()
    inv = Investigation(session_id="discord-abc", bot_message_id=12345, status="running")
    s.put(12345, inv)
    assert s.get(12345) is inv
    assert s.get(99999) is None


def test_conversation_state_clear():
    s = ConversationState()
    s.put(1, Investigation(session_id="s", bot_message_id=1, status="running"))
    s.clear(1)
    assert s.get(1) is None


def test_conversation_state_keyed_by_bot_message_id_for_reaction_lookup():
    """When a reaction arrives, we resolve via the bot's message_id (not the user's)."""
    s = ConversationState()
    inv = Investigation(session_id="discord-c-m", bot_message_id=42, status="completed")
    s.put(42, inv)
    assert s.get(42).session_id == "discord-c-m"
```

- [ ] **Step 2: Run, verify fail**

```bash
cd /Users/anhdungle/data/SRE/ai-sre-agent-incidentfox/discord-bot
.venv/bin/python -m pytest tests/test_state.py -v
```
Expected: ImportError for `state`.

- [ ] **Step 3: Implement `state.py`**

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from threading import RLock
from typing import Optional


@dataclass
class Investigation:
    session_id: str
    bot_message_id: int   # The Discord message_id of the bot's reply embed
    status: str           # "running" | "completed" | "failed"
    last_update_ms: int = 0


def _sanitize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def generate_session_id(*, channel_id: int, message_id: int) -> str:
    """K8s-safe session id: discord-<channel>-<message>, max 63 chars."""
    chan = _sanitize(str(channel_id))[:25]
    msg = _sanitize(str(message_id))[:25]
    return f"discord-{chan}-{msg}"


class ConversationState:
    """Thread-safe in-memory store. Keyed by the bot's reply message_id."""

    def __init__(self) -> None:
        self._items: dict[int, Investigation] = {}
        self._lock = RLock()

    def put(self, bot_message_id: int, inv: Investigation) -> None:
        with self._lock:
            self._items[bot_message_id] = inv

    def get(self, bot_message_id: int) -> Optional[Investigation]:
        with self._lock:
            return self._items.get(bot_message_id)

    def clear(self, bot_message_id: int) -> None:
        with self._lock:
            self._items.pop(bot_message_id, None)
```

- [ ] **Step 4: Run, verify pass (5 tests)**

```bash
.venv/bin/python -m pytest tests/test_state.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  add discord-bot/state.py discord-bot/tests/test_state.py
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  commit -m "feat(discord-bot): add conversation state and session id generator"
```

---

## Task 3: `markdown_utils.py` — Discord markdown chunking

Discord renders standard GitHub-flavored markdown inside embed `description`. The 4096-char hard limit forces chunking; we use 4000 for safety.

**Files:**
- Create: `discord-bot/markdown_utils.py`
- Test: `discord-bot/tests/test_markdown_utils.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

from markdown_utils import to_discord_md, escape_discord_md, split_for_embed_chunks


def test_passthrough_basic_formatting():
    assert to_discord_md("**bold**") == "**bold**"
    assert to_discord_md("*italic*") == "*italic*"
    assert to_discord_md("`code`") == "`code`"


def test_strip_slack_user_mentions():
    assert to_discord_md("hello <@U123>") == "hello"


def test_escape_discord_special_chars():
    # Discord uses backslash escaping for *, _, `, ~, |
    assert escape_discord_md("a*b") == r"a\*b"
    assert escape_discord_md("a_b") == r"a\_b"
    assert escape_discord_md("a`b") == r"a\`b"
    assert escape_discord_md("a~b") == r"a\~b"
    assert escape_discord_md("a|b") == r"a\|b"


def test_escape_handles_backslash_first():
    # backslash MUST be escaped first to avoid double-escaping
    assert escape_discord_md(r"\*") == r"\\\*"


def test_split_for_embed_chunks_under_limit_is_passthrough():
    text = "a" * 100
    chunks = split_for_embed_chunks(text, max_chars=200)
    assert chunks == [text]


def test_split_for_embed_chunks_at_paragraph_boundary():
    text = "para one\n\npara two\n\npara three"
    chunks = split_for_embed_chunks(text, max_chars=15)
    assert all(len(c) <= 15 + 2 for c in chunks)
    assert "para one" in chunks[0]
    assert chunks[-1].endswith("para three")


def test_split_for_embed_chunks_hard_split_long_paragraph():
    text = "x" * 50
    chunks = split_for_embed_chunks(text, max_chars=20)
    assert len(chunks) == 3
    assert all(len(c) <= 20 for c in chunks)


def test_split_default_max_is_4000_for_discord_safety_margin():
    text = "a" * 5000
    chunks = split_for_embed_chunks(text)  # default max_chars=4000
    assert all(len(c) <= 4000 for c in chunks)
    assert len(chunks) >= 2
```

- [ ] **Step 2: Run, verify fail**

```bash
.venv/bin/python -m pytest tests/test_markdown_utils.py -v
```

- [ ] **Step 3: Implement `markdown_utils.py`**

```python
from __future__ import annotations

import re

_SLACK_USER_MENTION_RE = re.compile(r"\s*<@[UW][A-Z0-9]+>")


def to_discord_md(text: str) -> str:
    """Convert agent-emitted markdown to Discord markdown.

    Discord supports standard GitHub-flavored markdown inside embed descriptions.
    Headings (#, ##) ARE rendered (unlike Lark cards). The only conversion needed:
    - Strip Slack-style user mentions (<@U123>) since Discord's mention syntax differs.
    """
    return _SLACK_USER_MENTION_RE.sub("", text)


def escape_discord_md(s: str) -> str:
    """Escape user-supplied text before inserting into a Discord embed.

    Discord markdown special chars: \\, *, _, `, ~, |
    Backslash must be escaped first to avoid double-escaping.
    """
    out = s.replace("\\", "\\\\")
    out = out.replace("*", "\\*")
    out = out.replace("_", "\\_")
    out = out.replace("`", "\\`")
    out = out.replace("~", "\\~")
    out = out.replace("|", "\\|")
    return out


def split_for_embed_chunks(text: str, *, max_chars: int = 4000) -> list[str]:
    """Split long text into Discord embed-description-friendly chunks.

    Discord's embed.description hard limit is 4096 chars; default is 4000 for safety.
    Prefer paragraph boundaries; fall back to hard split for runs longer than max_chars.
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
        for i in range(0, len(para), max_chars):
            chunks.append(para[i:i + max_chars])
    if buffer:
        chunks.append(buffer)
    return chunks
```

- [ ] **Step 4: Run, verify pass (8 tests)**

```bash
.venv/bin/python -m pytest tests/test_markdown_utils.py -v
```
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  add discord-bot/markdown_utils.py discord-bot/tests/test_markdown_utils.py
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  commit -m "feat(discord-bot): markdown converter for Discord embeds"
```

---

## Task 4: `embed_builder.py` — rich-embed composition

Discord embed structure: a single object with `title`, `description`, `color`, `fields[]`, `footer`. Color is a 24-bit RGB integer.

**Color constants:**
- Blue (running): `0x3498db` = 3447003
- Green (success): `0x2ecc71` = 3066993
- Red (failure): `0xe74c3c` = 15158332

**Files:**
- Create: `discord-bot/embed_builder.py`
- Test: `discord-bot/tests/test_embed_builder.py`

- [ ] **Step 1: Write failing test**

```python
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
```

- [ ] **Step 2: Run, verify fail**

```bash
.venv/bin/python -m pytest tests/test_embed_builder.py -v
```

- [ ] **Step 3: Implement `embed_builder.py`**

```python
from __future__ import annotations

from typing import Any

from markdown_utils import escape_discord_md, split_for_embed_chunks, to_discord_md

COLOR_BLUE = 0x3498DB    # 3447003
COLOR_GREEN = 0x2ECC71   # 3066993
COLOR_RED = 0xE74C3C     # 15158332

EmbedDict = dict[str, Any]

DESCRIPTION_HARD_LIMIT = 4096
DESCRIPTION_SAFE_LIMIT = 4000


def _truncate(text: str, *, limit: int = DESCRIPTION_HARD_LIMIT) -> str:
    if len(text) <= limit:
        return text
    suffix = "\n…(truncated, more coming)"
    return text[: limit - len(suffix)] + suffix


def build_status_embed(*, prompt: str) -> EmbedDict:
    safe = escape_discord_md(prompt)
    return {
        "title": "IncidentFox Investigation",
        "description": f"**Investigating…**\n\n> {safe}\n\n_This embed will update as I work._",
        "color": COLOR_BLUE,
    }


def build_streaming_embed(*, prompt: str, partial_text: str) -> EmbedDict:
    safe_prompt = escape_discord_md(prompt)
    body = to_discord_md(partial_text)
    description = f"**Investigating…**\n\n> {safe_prompt}\n\n---\n\n{body}"
    return {
        "title": "IncidentFox Investigation",
        "description": _truncate(description),
        "color": COLOR_BLUE,
    }


def build_final_embed(*, prompt: str, result_text: str, success: bool) -> EmbedDict:
    safe_prompt = escape_discord_md(prompt)
    body = to_discord_md(result_text)
    description = f"**Question**\n\n> {safe_prompt}\n\n---\n\n{body}"
    return {
        "title": "Investigation Complete" if success else "Investigation Failed",
        "description": _truncate(description),
        "color": COLOR_GREEN if success else COLOR_RED,
    }


def build_error_embed(*, prompt: str, error: str) -> EmbedDict:
    safe_prompt = escape_discord_md(prompt)
    safe_err = escape_discord_md(error)
    return {
        "title": "Investigation Failed",
        "description": f"**Question**\n\n> {safe_prompt}\n\n---\n\n**Error:** {safe_err}",
        "color": COLOR_RED,
    }


def embeds_for_long_result(
    *, prompt: str, result_text: str, success: bool
) -> list[EmbedDict]:
    """Build one or more embeds for a final result that may exceed 4096 chars.

    First embed is the primary (with question + first chunk). Subsequent embeds
    are continuation chunks tagged with a 'continued' footer.
    """
    safe_prompt = escape_discord_md(prompt)
    body = to_discord_md(result_text)
    chunks = split_for_embed_chunks(body, max_chars=DESCRIPTION_SAFE_LIMIT - 200)

    primary = {
        "title": "Investigation Complete" if success else "Investigation Failed",
        "description": f"**Question**\n\n> {safe_prompt}\n\n---\n\n{chunks[0]}",
        "color": COLOR_GREEN if success else COLOR_RED,
    }
    embeds: list[EmbedDict] = [primary]
    for i, chunk in enumerate(chunks[1:], start=2):
        embeds.append({
            "title": "Investigation (continued)",
            "description": chunk,
            "color": COLOR_GREEN if success else COLOR_RED,
            "footer": {"text": f"continued · part {i}/{len(chunks)}"},
        })
    return embeds
```

- [ ] **Step 4: Run, verify pass (7 tests)**

```bash
.venv/bin/python -m pytest tests/test_embed_builder.py -v
```
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  add discord-bot/embed_builder.py discord-bot/tests/test_embed_builder.py
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  commit -m "feat(discord-bot): rich-embed builder for status/streaming/final/error"
```

---

## Task 5: `event_router.py` — normalize Discord events

The `gateway_client.py` will pass discord.py message objects into `event_router.normalize_message()`, which extracts only what we need into a plain dataclass for the rest of the pipeline.

**Files:**
- Create: `discord-bot/event_router.py`
- Test: `discord-bot/tests/test_event_router.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

import pytest

from event_router import DiscordMessageEvent, normalize_message


class _FakeAuthor:
    def __init__(self, id: int, bot: bool = False) -> None:
        self.id = id
        self.bot = bot


class _FakeMessage:
    def __init__(
        self,
        *,
        msg_id: int = 1,
        channel_id: int = 100,
        guild_id: int = 1000,
        author: _FakeAuthor,
        content: str = "",
        mentions: list[_FakeAuthor] | None = None,
    ) -> None:
        self.id = msg_id
        self.channel = type("C", (), {"id": channel_id})()
        self.guild = type("G", (), {"id": guild_id})()
        self.author = author
        self.content = content
        self.mentions = mentions or []


def test_normalize_at_mention_strips_mention_and_returns_event():
    bot_user_id = 999
    user = _FakeAuthor(id=42)
    bot = _FakeAuthor(id=bot_user_id, bot=True)
    msg = _FakeMessage(
        author=user,
        content="<@999> why is checkout slow?",
        mentions=[bot],
    )
    evt = normalize_message(msg, bot_user_id=bot_user_id)
    assert isinstance(evt, DiscordMessageEvent)
    assert evt.message_id == 1
    assert evt.channel_id == 100
    assert evt.guild_id == 1000
    assert evt.author_id == 42
    assert evt.is_mention is True
    assert evt.text_after_mention == "why is checkout slow?"


def test_normalize_handles_nickname_mention_format():
    """Discord uses both <@123> and <@!123> (the nickname form)."""
    bot_user_id = 999
    user = _FakeAuthor(id=42)
    bot = _FakeAuthor(id=bot_user_id, bot=True)
    msg = _FakeMessage(
        author=user,
        content="<@!999> hello",
        mentions=[bot],
    )
    evt = normalize_message(msg, bot_user_id=bot_user_id)
    assert evt.text_after_mention == "hello"


def test_normalize_returns_none_when_message_is_from_bot_itself():
    bot_user_id = 999
    msg = _FakeMessage(author=_FakeAuthor(id=bot_user_id, bot=True), content="anything")
    assert normalize_message(msg, bot_user_id=bot_user_id) is None


def test_normalize_returns_none_when_message_has_no_bot_mention():
    bot_user_id = 999
    other_bot = _FakeAuthor(id=111, bot=True)
    msg = _FakeMessage(
        author=_FakeAuthor(id=42),
        content="<@111> hi",
        mentions=[other_bot],
    )
    assert normalize_message(msg, bot_user_id=bot_user_id) is None


def test_normalize_returns_none_when_outside_bound_guild():
    bot_user_id = 999
    msg = _FakeMessage(
        msg_id=1, channel_id=100, guild_id=8888,
        author=_FakeAuthor(id=42),
        content="<@999> hello",
        mentions=[_FakeAuthor(id=bot_user_id, bot=True)],
    )
    assert normalize_message(msg, bot_user_id=bot_user_id, bound_guild_id=1000) is None


def test_normalize_passes_when_in_bound_guild():
    bot_user_id = 999
    msg = _FakeMessage(
        msg_id=1, channel_id=100, guild_id=1000,
        author=_FakeAuthor(id=42),
        content="<@999> hello",
        mentions=[_FakeAuthor(id=bot_user_id, bot=True)],
    )
    evt = normalize_message(msg, bot_user_id=bot_user_id, bound_guild_id=1000)
    assert evt is not None
```

- [ ] **Step 2: Run, verify fail**

```bash
.venv/bin/python -m pytest tests/test_event_router.py -v
```

- [ ] **Step 3: Implement `event_router.py`**

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class DiscordMessageEvent:
    message_id: int
    channel_id: int
    guild_id: int
    author_id: int
    text_after_mention: str
    is_mention: bool


def _strip_mentions_for_user(text: str, user_id: int) -> str:
    """Remove all forms of <@USER_ID> and <@!USER_ID> mention strings for the given user."""
    pattern = re.compile(rf"<@!?{user_id}>")
    return pattern.sub("", text).strip()


def normalize_message(
    message: Any,
    *,
    bot_user_id: int,
    bound_guild_id: Optional[int] = None,
) -> Optional[DiscordMessageEvent]:
    """Normalize a discord.py Message into a unified event dataclass.

    Returns None to indicate the message should be ignored:
    - Bot's own messages
    - Messages without an @-mention of this bot
    - Messages outside `bound_guild_id` if specified
    """
    # Filter: bot's own messages
    if getattr(message.author, "id", None) == bot_user_id:
        return None
    if getattr(message.author, "bot", False) is True and message.author.id == bot_user_id:
        return None

    # Filter: outside bound guild
    if bound_guild_id is not None and getattr(message.guild, "id", None) != bound_guild_id:
        return None

    # Filter: must mention this bot
    mention_ids = {getattr(m, "id", None) for m in (message.mentions or [])}
    if bot_user_id not in mention_ids:
        return None

    text = _strip_mentions_for_user(message.content or "", bot_user_id)

    return DiscordMessageEvent(
        message_id=message.id,
        channel_id=message.channel.id,
        guild_id=message.guild.id,
        author_id=message.author.id,
        text_after_mention=text,
        is_mention=True,
    )
```

- [ ] **Step 4: Run, verify pass (6 tests)**

```bash
.venv/bin/python -m pytest tests/test_event_router.py -v
```

- [ ] **Step 5: Commit**

```bash
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  add discord-bot/event_router.py discord-bot/tests/test_event_router.py
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  commit -m "feat(discord-bot): normalize Discord events with guild + mention filters"
```

---

## Task 6: `orchestrator_client.py` — SSE consumer

This client mirrors `lark-bot/orchestrator_client.py` exactly — same shape, same orchestrator endpoint, same error handling.

**Files:**
- Create: `discord-bot/orchestrator_client.py`
- Test: `discord-bot/tests/test_orchestrator_client.py`

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
    respx.post("http://orch:8070/api/v1/agents/dispatch-stream").mock(
        return_value=httpx.Response(200, content=sse, headers={"content-type": "text/event-stream"})
    )
    client = OrchestratorClient(base_url="http://orch:8070", team_token="tok")
    events = [e async for e in client.stream_agent(message="hi", session_id="s")]
    assert [e["type"] for e in events] == ["tool_use", "complete"]
    await client.aclose()


@respx.mock
async def test_stream_raises_on_4xx():
    respx.post("http://orch:8070/api/v1/agents/dispatch-stream").mock(
        return_value=httpx.Response(401, json={"error": "unauthorized"})
    )
    client = OrchestratorClient(base_url="http://orch:8070", team_token="bad")
    with pytest.raises(OrchestratorError):
        async for _ in client.stream_agent(message="hi", session_id="s"):
            pass
    await client.aclose()
```

- [ ] **Step 2: Run, verify fail**

```bash
.venv/bin/python -m pytest tests/test_orchestrator_client.py -v
```

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

- [ ] **Step 4: Run, verify pass (2 tests)**

```bash
.venv/bin/python -m pytest tests/test_orchestrator_client.py -v
```

- [ ] **Step 5: Commit**

```bash
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  add discord-bot/orchestrator_client.py discord-bot/tests/test_orchestrator_client.py
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  commit -m "feat(discord-bot): orchestrator SSE streaming client"
```

---

## Task 7: `stream_handler.py` — debounced embed-edit consumer

Mirror of lark-bot's stream_handler — accepts an async iterator of agent events, drives `on_update` (debounced) and `on_final` callbacks. Transport-agnostic; the investigation_handler wires it to discord-specific embed edits.

**Files:**
- Create: `discord-bot/stream_handler.py`
- Test: `discord-bot/tests/test_stream_handler.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

import pytest

from stream_handler import handle_stream


def _events(*items):
    async def gen():
        for it in items:
            yield it
    return gen()


@pytest.mark.asyncio
async def test_calls_update_then_final_on_complete():
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
    assert updates == ["Looking…", "Looking… at logs."]
    assert finals == [("Looking… at logs.", True)]


@pytest.mark.asyncio
async def test_failure_event_marks_unsuccessful():
    finals: list[tuple[str, bool]] = []

    async def on_update(_: str): pass
    async def on_final(text: str, success: bool):
        finals.append((text, success))

    src = _events({"type": "error", "error": "boom"})
    await handle_stream(src, on_update=on_update, on_final=on_final, debounce_ms=0)
    assert finals == [("boom", False)]


@pytest.mark.asyncio
async def test_debounce_collapses_rapid_updates():
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
    assert updates[-1] == "abc" or updates == []
```

- [ ] **Step 2: Run, verify fail**

```bash
.venv/bin/python -m pytest tests/test_stream_handler.py -v
```

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

    if not final_called:
        await on_final(buffer, True)
```

- [ ] **Step 4: Run, verify pass (3 tests)**

```bash
.venv/bin/python -m pytest tests/test_stream_handler.py -v
```

- [ ] **Step 5: Commit**

```bash
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  add discord-bot/stream_handler.py discord-bot/tests/test_stream_handler.py
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  commit -m "feat(discord-bot): SSE stream handler with debounced updates"
```

---

## Task 8: `feedback_handler.py` — reaction → config-service POST

The `feedback_handler` accepts a normalized reaction event and POSTs to config-service. Phase 1 spec specifies endpoint `POST /api/v1/feedback`. If config-service hasn't yet implemented this endpoint, the handler still POSTs and the call fails gracefully — we log the failure and continue (the agent flow doesn't depend on feedback success).

**Files:**
- Create: `discord-bot/feedback_handler.py`
- Test: `discord-bot/tests/test_feedback_handler.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

import httpx
import pytest
import respx

from feedback_handler import FeedbackHandler, ReactionType
from state import ConversationState, Investigation


@respx.mock
async def test_thumbs_up_posts_to_config_service():
    state = ConversationState()
    state.put(42, Investigation(session_id="discord-c-m", bot_message_id=42, status="completed"))

    route = respx.post("http://config:8080/api/v1/feedback").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )

    handler = FeedbackHandler(
        config_service_url="http://config:8080",
        team_token="tok",
        state=state,
    )
    await handler.handle_reaction(
        reaction=ReactionType.THUMBS_UP,
        bot_message_id=42,
        user_id=12345,
    )

    assert route.called
    body = route.calls.last.request.read().decode()
    assert "discord-c-m" in body
    assert "thumbs_up" in body
    assert "12345" in body
    await handler.aclose()


@respx.mock
async def test_thumbs_down_posts_with_correct_reaction_field():
    state = ConversationState()
    state.put(42, Investigation(session_id="s", bot_message_id=42, status="completed"))

    route = respx.post("http://config:8080/api/v1/feedback").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    handler = FeedbackHandler(config_service_url="http://config:8080", team_token="t", state=state)
    await handler.handle_reaction(reaction=ReactionType.THUMBS_DOWN, bot_message_id=42, user_id=1)
    body = route.calls.last.request.read().decode()
    assert "thumbs_down" in body
    await handler.aclose()


@respx.mock
async def test_reaction_on_unknown_message_is_silently_ignored():
    state = ConversationState()  # empty
    route = respx.post("http://config:8080/api/v1/feedback").mock(
        return_value=httpx.Response(200)
    )
    handler = FeedbackHandler(config_service_url="http://config:8080", team_token="t", state=state)
    await handler.handle_reaction(reaction=ReactionType.THUMBS_UP, bot_message_id=99999, user_id=1)
    assert not route.called  # No POST when message_id has no investigation
    await handler.aclose()


@respx.mock
async def test_config_service_failure_is_swallowed():
    state = ConversationState()
    state.put(42, Investigation(session_id="s", bot_message_id=42, status="completed"))

    respx.post("http://config:8080/api/v1/feedback").mock(
        return_value=httpx.Response(503, json={"error": "down"})
    )
    handler = FeedbackHandler(config_service_url="http://config:8080", team_token="t", state=state)
    # Must NOT raise — feedback failures are non-fatal.
    await handler.handle_reaction(reaction=ReactionType.THUMBS_UP, bot_message_id=42, user_id=1)
    await handler.aclose()
```

- [ ] **Step 2: Run, verify fail**

```bash
.venv/bin/python -m pytest tests/test_feedback_handler.py -v
```

- [ ] **Step 3: Implement**

```python
from __future__ import annotations

import enum
import json
from typing import Any

import httpx

from state import ConversationState


def _log(event: str, **fields: Any) -> None:
    try:
        print(json.dumps({"service": "discord-bot", "component": "feedback", "event": event, **fields}, default=str))
    except Exception:
        print(f"{event} {fields}")


class ReactionType(str, enum.Enum):
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"


class FeedbackHandler:
    def __init__(
        self,
        *,
        config_service_url: str,
        team_token: str,
        state: ConversationState,
        timeout: float = 5.0,
    ) -> None:
        self._url = config_service_url.rstrip("/")
        self._http = httpx.AsyncClient(
            timeout=timeout,
            headers={"Authorization": f"Bearer {team_token}", "Content-Type": "application/json"},
        )
        self._state = state

    async def handle_reaction(
        self,
        *,
        reaction: ReactionType,
        bot_message_id: int,
        user_id: int,
    ) -> None:
        inv = self._state.get(bot_message_id)
        if inv is None:
            _log("reaction_on_unknown_message", bot_message_id=bot_message_id)
            return

        body = {
            "session_id": inv.session_id,
            "user_id": str(user_id),
            "reaction": reaction.value,
            "source": "discord",
        }

        try:
            resp = await self._http.post(f"{self._url}/api/v1/feedback", json=body)
            if resp.status_code >= 400:
                _log("feedback_post_non_2xx", status=resp.status_code, body=resp.text[:200])
            else:
                _log("feedback_recorded", session_id=inv.session_id, reaction=reaction.value)
        except httpx.HTTPError as e:
            _log("feedback_post_failed", error=str(e))

    async def aclose(self) -> None:
        await self._http.aclose()
```

- [ ] **Step 4: Run, verify pass (4 tests)**

```bash
.venv/bin/python -m pytest tests/test_feedback_handler.py -v
```

- [ ] **Step 5: Commit**

```bash
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  add discord-bot/feedback_handler.py discord-bot/tests/test_feedback_handler.py
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  commit -m "feat(discord-bot): reaction-feedback handler posting to config-service"
```

---

## Task 9: `investigation_handler.py` — lifecycle glue

Ties together: receive `DiscordMessageEvent` → post initial status embed → call orchestrator → drive stream_handler → patch embed on each update / final → add 👍/👎 reactions.

**Files:**
- Create: `discord-bot/investigation_handler.py`
- Test: `discord-bot/tests/test_investigation_handler.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

import pytest

from event_router import DiscordMessageEvent
from investigation_handler import InvestigationHandler


class FakeDiscordChannel:
    def __init__(self) -> None:
        self.posted: list[dict] = []
        self.edits: list[tuple[int, dict]] = []
        self.reactions: list[tuple[int, str]] = []
        self._next_msg_id = 5000

    async def send_embed(self, *, channel_id: int, reply_to_message_id: int, embed: dict) -> int:
        self.posted.append({"channel_id": channel_id, "reply_to": reply_to_message_id, "embed": embed})
        msg_id = self._next_msg_id
        self._next_msg_id += 1
        return msg_id

    async def edit_embed(self, *, message_id: int, embed: dict) -> None:
        self.edits.append((message_id, embed))

    async def add_reaction(self, *, message_id: int, emoji: str) -> None:
        self.reactions.append((message_id, emoji))


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
async def test_investigation_full_happy_path():
    channel = FakeDiscordChannel()
    orch = FakeOrchestrator()
    handler = InvestigationHandler(
        discord=channel,
        orchestrator=orch,
        org_id="o",
        team_id="t",
        debounce_ms=0,
    )
    evt = DiscordMessageEvent(
        message_id=1, channel_id=100, guild_id=1000, author_id=42,
        text_after_mention="why is checkout slow?", is_mention=True,
    )
    await handler.handle(evt)

    # Posted initial embed
    assert len(channel.posted) == 1
    assert "Investigating" in channel.posted[0]["embed"]["description"]

    # Final embed edit is green/Complete
    assert len(channel.edits) >= 1
    final_msg_id, final_embed = channel.edits[-1]
    assert final_embed["title"] == "Investigation Complete"

    # Reactions added (👍 and 👎)
    emojis = [r[1] for r in channel.reactions]
    assert "👍" in emojis
    assert "👎" in emojis


@pytest.mark.asyncio
async def test_orchestrator_failure_yields_error_embed():
    class BoomOrchestrator:
        async def stream_agent(self, **kwargs):
            raise RuntimeError("orchestrator unreachable")
            yield  # pragma: no cover

        async def aclose(self): pass

    channel = FakeDiscordChannel()
    handler = InvestigationHandler(discord=channel, orchestrator=BoomOrchestrator(), org_id="o", team_id="t", debounce_ms=0)
    await handler.handle(DiscordMessageEvent(
        message_id=1, channel_id=100, guild_id=1000, author_id=42,
        text_after_mention="x", is_mention=True,
    ))
    final_embed = channel.edits[-1][1]
    assert final_embed["title"] == "Investigation Failed"
    assert "orchestrator unreachable" in final_embed["description"]


@pytest.mark.asyncio
async def test_empty_prompt_is_skipped():
    channel = FakeDiscordChannel()
    handler = InvestigationHandler(discord=channel, orchestrator=FakeOrchestrator(), org_id="o", team_id="t", debounce_ms=0)
    await handler.handle(DiscordMessageEvent(
        message_id=1, channel_id=100, guild_id=1000, author_id=42,
        text_after_mention="   ", is_mention=True,
    ))
    assert channel.posted == []
    assert channel.edits == []
```

- [ ] **Step 2: Run, verify fail**

```bash
.venv/bin/python -m pytest tests/test_investigation_handler.py -v
```

- [ ] **Step 3: Implement**

```python
from __future__ import annotations

import json
from typing import Any, Protocol

from embed_builder import (
    build_error_embed,
    build_final_embed,
    build_status_embed,
    build_streaming_embed,
)
from event_router import DiscordMessageEvent
from state import ConversationState, Investigation, generate_session_id
from stream_handler import handle_stream


def _log(event: str, **fields: Any) -> None:
    try:
        print(json.dumps({"service": "discord-bot", "component": "investigation", "event": event, **fields}, default=str))
    except Exception:
        print(f"{event} {fields}")


class _Discord(Protocol):
    async def send_embed(self, *, channel_id: int, reply_to_message_id: int, embed: dict) -> int: ...
    async def edit_embed(self, *, message_id: int, embed: dict) -> None: ...
    async def add_reaction(self, *, message_id: int, emoji: str) -> None: ...


class _Orchestrator(Protocol):
    def stream_agent(self, **kwargs): ...
    async def aclose(self) -> None: ...


class InvestigationHandler:
    def __init__(
        self,
        *,
        discord: _Discord,
        orchestrator: _Orchestrator,
        org_id: str,
        team_id: str,
        state: ConversationState | None = None,
        debounce_ms: int = 250,
    ) -> None:
        self._discord = discord
        self._orch = orchestrator
        self._org_id = org_id
        self._team_id = team_id
        self._state = state or ConversationState()
        self._debounce_ms = debounce_ms

    @property
    def state(self) -> ConversationState:
        return self._state

    async def handle(self, evt: DiscordMessageEvent) -> None:
        prompt = (evt.text_after_mention or "").strip()
        if not prompt:
            _log("empty_prompt_skipped", message_id=evt.message_id)
            return

        session_id = generate_session_id(channel_id=evt.channel_id, message_id=evt.message_id)
        status_embed = build_status_embed(prompt=prompt)
        bot_message_id = await self._discord.send_embed(
            channel_id=evt.channel_id,
            reply_to_message_id=evt.message_id,
            embed=status_embed,
        )
        self._state.put(bot_message_id, Investigation(
            session_id=session_id, bot_message_id=bot_message_id, status="running",
        ))
        _log("posted_status_embed", session_id=session_id, bot_message_id=bot_message_id)

        try:
            async def on_update(text: str) -> None:
                embed = build_streaming_embed(prompt=prompt, partial_text=text)
                await self._discord.edit_embed(message_id=bot_message_id, embed=embed)

            async def on_final(text: str, success: bool) -> None:
                embed = build_final_embed(prompt=prompt, result_text=text, success=success)
                await self._discord.edit_embed(message_id=bot_message_id, embed=embed)
                # Add feedback reactions
                try:
                    await self._discord.add_reaction(message_id=bot_message_id, emoji="👍")
                    await self._discord.add_reaction(message_id=bot_message_id, emoji="👎")
                except Exception as e:
                    _log("reaction_add_failed", error=str(e))
                # Update state status (kept in state for reaction lookup)
                inv = self._state.get(bot_message_id)
                if inv:
                    inv.status = "completed" if success else "failed"

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
            await self._discord.edit_embed(
                message_id=bot_message_id,
                embed=build_error_embed(prompt=prompt, error=str(e)),
            )
```

- [ ] **Step 4: Run, verify pass (3 tests)**

```bash
.venv/bin/python -m pytest tests/test_investigation_handler.py -v
```

- [ ] **Step 5: Commit**

```bash
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  add discord-bot/investigation_handler.py discord-bot/tests/test_investigation_handler.py
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  commit -m "feat(discord-bot): investigation lifecycle handler with reactions"
```

---

## Task 10: `gateway_client.py` — discord.py Bot wiring

Wraps discord.py's Client/Bot. The smoke test verifies the constructor accepts a handler and that the discord.Intents are configured correctly. Full WebSocket testing isn't possible without real Discord credentials.

**Files:**
- Create: `discord-bot/gateway_client.py`
- Test: `discord-bot/tests/test_gateway_client.py` (smoke only)

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

from gateway_client import DiscordGatewayClient


class StubInvestigationHandler:
    async def handle(self, evt) -> None:
        pass

    @property
    def state(self):
        return None


class StubFeedbackHandler:
    async def handle_reaction(self, **kwargs) -> None:
        pass


def test_constructor_accepts_handlers_and_token():
    """Smoke test — construct without network access."""
    client = DiscordGatewayClient(
        bot_token="fake-token",
        guild_id=1234567890,
        investigation_handler=StubInvestigationHandler(),
        feedback_handler=StubFeedbackHandler(),
    )
    assert client is not None


def test_intents_include_message_content_and_reactions():
    """Critical: privileged intents must be enabled for the bot to receive messages and reactions."""
    client = DiscordGatewayClient(
        bot_token="fake",
        guild_id=1,
        investigation_handler=StubInvestigationHandler(),
        feedback_handler=StubFeedbackHandler(),
    )
    intents = client._intents()
    assert intents.message_content is True
    assert intents.guild_messages is True
    assert intents.guild_reactions is True
    assert intents.guilds is True
```

- [ ] **Step 2: Run, verify fail**

```bash
.venv/bin/python -m pytest tests/test_gateway_client.py -v
```

- [ ] **Step 3: Implement**

```python
from __future__ import annotations

import json
from typing import Any, Protocol

import discord

from event_router import normalize_message
from feedback_handler import ReactionType


def _log(event: str, **fields: Any) -> None:
    try:
        print(json.dumps({"service": "discord-bot", "component": "gateway", "event": event, **fields}, default=str))
    except Exception:
        print(f"{event} {fields}")


class _InvestigationHandler(Protocol):
    async def handle(self, evt) -> None: ...
    @property
    def state(self): ...


class _FeedbackHandler(Protocol):
    async def handle_reaction(self, *, reaction: ReactionType, bot_message_id: int, user_id: int) -> None: ...


class DiscordAdapter:
    """Concrete _Discord protocol implementation backed by discord.py."""

    def __init__(self, client: "discord.Client") -> None:
        self._client = client

    async def send_embed(self, *, channel_id: int, reply_to_message_id: int, embed: dict) -> int:
        channel = self._client.get_channel(channel_id) or await self._client.fetch_channel(channel_id)
        ref_msg = await channel.fetch_message(reply_to_message_id)
        sent = await ref_msg.reply(embed=discord.Embed.from_dict(embed))
        return sent.id

    async def edit_embed(self, *, message_id: int, embed: dict) -> None:
        # We need a channel to fetch the message; we don't track the channel here, so the handler
        # should pass channel context via the state. For Phase 1 we stash the channel on the
        # handler at send time. Until then, we store the discord.Message object in state.
        # See investigation_handler — the bot_message_id we return is the discord Message.id
        # but we keep a separate adapter that retains the message object.
        raise NotImplementedError("Use ChannelAwareDiscordAdapter")

    async def add_reaction(self, *, message_id: int, emoji: str) -> None:
        raise NotImplementedError("Use ChannelAwareDiscordAdapter")


class ChannelAwareDiscordAdapter:
    """Adapter that retains discord.Message objects so edit/react are possible without a channel hint."""

    def __init__(self, client: "discord.Client") -> None:
        self._client = client
        self._messages: dict[int, "discord.Message"] = {}

    async def send_embed(self, *, channel_id: int, reply_to_message_id: int, embed: dict) -> int:
        channel = self._client.get_channel(channel_id) or await self._client.fetch_channel(channel_id)
        ref_msg = await channel.fetch_message(reply_to_message_id)
        sent = await ref_msg.reply(embed=discord.Embed.from_dict(embed))
        self._messages[sent.id] = sent
        return sent.id

    async def edit_embed(self, *, message_id: int, embed: dict) -> None:
        msg = self._messages.get(message_id)
        if msg is None:
            return
        await msg.edit(embed=discord.Embed.from_dict(embed))

    async def add_reaction(self, *, message_id: int, emoji: str) -> None:
        msg = self._messages.get(message_id)
        if msg is None:
            return
        await msg.add_reaction(emoji)


class DiscordGatewayClient:
    """discord.py Client wired to investigation_handler + feedback_handler."""

    def __init__(
        self,
        *,
        bot_token: str,
        guild_id: int,
        investigation_handler: _InvestigationHandler,
        feedback_handler: _FeedbackHandler,
    ) -> None:
        self._token = bot_token
        self._guild_id = guild_id
        self._investigation = investigation_handler
        self._feedback = feedback_handler
        self._client = discord.Client(intents=self._intents())
        self._adapter = ChannelAwareDiscordAdapter(self._client)
        self._register_handlers()

    def _intents(self) -> discord.Intents:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guild_messages = True
        intents.guild_reactions = True
        intents.guilds = True
        return intents

    def _register_handlers(self) -> None:
        @self._client.event
        async def on_ready():
            _log("gateway_ready", bot_user_id=self._client.user.id)

        @self._client.event
        async def on_message(message: discord.Message):
            try:
                evt = normalize_message(
                    message,
                    bot_user_id=self._client.user.id,
                    bound_guild_id=self._guild_id,
                )
                if evt is None:
                    return
                # Inject the adapter into the investigation handler. Investigation_handler
                # was constructed with a placeholder; we inject the real one here.
                # Cleaner alternative: pass adapter into investigation_handler at construction.
                self._investigation._discord = self._adapter  # type: ignore[attr-defined]
                await self._investigation.handle(evt)
            except Exception as e:
                _log("on_message_error", error=str(e))

        @self._client.event
        async def on_reaction_add(reaction: discord.Reaction, user: discord.User):
            try:
                # Ignore bot's own reactions
                if user.bot or user.id == self._client.user.id:
                    return
                # Only act on reactions on the bot's own messages
                if reaction.message.author.id != self._client.user.id:
                    return
                rtype = _emoji_to_reaction_type(str(reaction.emoji))
                if rtype is None:
                    return
                await self._feedback.handle_reaction(
                    reaction=rtype,
                    bot_message_id=reaction.message.id,
                    user_id=user.id,
                )
            except Exception as e:
                _log("on_reaction_add_error", error=str(e))

    async def run(self) -> None:
        await self._client.start(self._token)


def _emoji_to_reaction_type(emoji: str):
    """Map a Discord emoji string to a ReactionType (or None)."""
    if emoji == "👍":
        return ReactionType.THUMBS_UP
    if emoji == "👎":
        return ReactionType.THUMBS_DOWN
    return None
```

- [ ] **Step 4: Run, verify pass (2 tests)**

```bash
.venv/bin/python -m pytest tests/test_gateway_client.py -v
```

- [ ] **Step 5: Commit**

```bash
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  add discord-bot/gateway_client.py discord-bot/tests/test_gateway_client.py
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  commit -m "feat(discord-bot): discord.py Gateway client with on_message + on_reaction"
```

---

## Task 11: `healthz.py` — minimal aiohttp /healthz server

A tiny HTTP server for K8s liveness/readiness probes. No business logic.

**Files:**
- Create: `discord-bot/healthz.py`
- Test: (skipped — trivial; covered by app smoke test)

- [ ] **Step 1: Implement**

```python
from __future__ import annotations

from aiohttp import web


def build_healthz_app() -> web.Application:
    app = web.Application()

    async def healthz(request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    app.router.add_get("/healthz", healthz)
    return app


async def run_healthz(port: int) -> None:
    """Run the healthz server on the given port. Returns when stopped."""
    app = build_healthz_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    # Block forever (until cancelled)
    import asyncio
    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
```

- [ ] **Step 2: Commit**

```bash
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  add discord-bot/healthz.py
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  commit -m "feat(discord-bot): aiohttp /healthz endpoint for K8s probes"
```

---

## Task 12: `app.py` — service entry

Wires everything: env validation, instantiates all components, runs gateway + healthz concurrently.

**Files:**
- Create: `discord-bot/app.py`
- Test: `discord-bot/tests/test_app_smoke.py`

- [ ] **Step 1: Write failing test**

```python
from __future__ import annotations

import pytest

from app import build_settings, SettingsError


def test_settings_requires_bot_token(monkeypatch):
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    with pytest.raises(SettingsError):
        build_settings()


def test_settings_requires_guild_id(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "x")
    monkeypatch.delenv("DISCORD_GUILD_ID", raising=False)
    with pytest.raises(SettingsError):
        build_settings()


def test_settings_with_all_required_present(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "fake")
    monkeypatch.setenv("DISCORD_APP_ID", "111")
    monkeypatch.setenv("DISCORD_GUILD_ID", "222")
    monkeypatch.setenv("INCIDENTFOX_TEAM_TOKEN", "tok")
    monkeypatch.setenv("INCIDENTFOX_ORG_ID", "o")
    monkeypatch.setenv("INCIDENTFOX_TEAM_ID", "t")
    s = build_settings()
    assert s.bot_token == "fake"
    assert s.guild_id == 222
    assert s.org_id == "o"


def test_settings_rejects_non_integer_guild_id(monkeypatch):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "fake")
    monkeypatch.setenv("DISCORD_APP_ID", "111")
    monkeypatch.setenv("DISCORD_GUILD_ID", "not-a-number")
    monkeypatch.setenv("INCIDENTFOX_TEAM_TOKEN", "tok")
    monkeypatch.setenv("INCIDENTFOX_ORG_ID", "o")
    monkeypatch.setenv("INCIDENTFOX_TEAM_ID", "t")
    with pytest.raises(SettingsError):
        build_settings()
```

- [ ] **Step 2: Run, verify fail**

```bash
.venv/bin/python -m pytest tests/test_app_smoke.py -v
```

- [ ] **Step 3: Implement**

```python
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from dataclasses import dataclass

from dotenv import load_dotenv

from feedback_handler import FeedbackHandler
from gateway_client import DiscordGatewayClient
from healthz import run_healthz
from investigation_handler import InvestigationHandler
from orchestrator_client import OrchestratorClient
from state import ConversationState

logger = logging.getLogger("discord-bot")


class SettingsError(Exception):
    pass


@dataclass
class Settings:
    bot_token: str
    app_id: str
    guild_id: int
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
    guild_id_raw = _require("DISCORD_GUILD_ID")
    try:
        guild_id = int(guild_id_raw)
    except ValueError as e:
        raise SettingsError(f"DISCORD_GUILD_ID must be an integer, got: {guild_id_raw!r}") from e

    return Settings(
        bot_token=_require("DISCORD_BOT_TOKEN"),
        app_id=_require("DISCORD_APP_ID"),
        guild_id=guild_id,
        orchestrator_url=os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8070"),
        config_service_url=os.environ.get("CONFIG_SERVICE_URL", "http://config-service:8080"),
        team_token=_require("INCIDENTFOX_TEAM_TOKEN"),
        org_id=_require("INCIDENTFOX_ORG_ID"),
        team_id=_require("INCIDENTFOX_TEAM_ID"),
        internal_http_port=int(os.environ.get("INTERNAL_HTTP_PORT", "8080")),
    )


async def _serve(s: Settings) -> None:
    state = ConversationState()
    orchestrator = OrchestratorClient(base_url=s.orchestrator_url, team_token=s.team_token)
    feedback = FeedbackHandler(
        config_service_url=s.config_service_url,
        team_token=s.team_token,
        state=state,
    )

    # InvestigationHandler is constructed with a placeholder discord adapter; the real adapter
    # is injected by gateway_client at on_message time (since the discord.Client must be
    # constructed before the adapter can hold a reference to it).
    class _DiscordPlaceholder:
        async def send_embed(self, **kw): raise RuntimeError("adapter not yet wired")
        async def edit_embed(self, **kw): raise RuntimeError("adapter not yet wired")
        async def add_reaction(self, **kw): raise RuntimeError("adapter not yet wired")

    investigation = InvestigationHandler(
        discord=_DiscordPlaceholder(),
        orchestrator=orchestrator,
        org_id=s.org_id,
        team_id=s.team_id,
        state=state,
    )

    gateway = DiscordGatewayClient(
        bot_token=s.bot_token,
        guild_id=s.guild_id,
        investigation_handler=investigation,
        feedback_handler=feedback,
    )

    stop = asyncio.Event()

    def _signal_handler(*_: object) -> None:
        stop.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            asyncio.get_running_loop().add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass

    tasks = [
        asyncio.create_task(gateway.run(), name="gateway"),
        asyncio.create_task(run_healthz(s.internal_http_port), name="healthz"),
        asyncio.create_task(stop.wait(), name="stop"),
    ]

    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()

    await orchestrator.aclose()
    await feedback.aclose()


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = build_settings()
    print(json.dumps({"service": "discord-bot", "event": "starting", "guild_id": settings.guild_id}))
    asyncio.run(_serve(settings))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run, verify pass (4 tests)**

```bash
.venv/bin/python -m pytest tests/test_app_smoke.py -v
```

Also run the full discord-bot test suite to confirm no regressions:

```bash
.venv/bin/python -m pytest tests/ -q
```

Expected: ≥35 passed (sum across tasks 2-12).

- [ ] **Step 5: Commit**

```bash
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  add discord-bot/app.py discord-bot/tests/test_app_smoke.py
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  commit -m "feat(discord-bot): service entry with env validation and lifecycle"
```

---

## Task 13: Helm chart template + values

**Files:**
- Create: `charts/incidentfox/templates/discord-bot.yaml`
- Modify: `charts/incidentfox/templates/external-secrets.yaml` (add discordBot block)
- Modify: `charts/incidentfox/values.yaml` (add `services.discordBot` + `externalSecrets.contract.discordBot`)
- Modify: `charts/incidentfox/values.pilot.yaml` (enable for the rollout)

- [ ] **Step 1: Read lark-bot template + values for reference**

```bash
sed -n '1,80p' /Users/anhdungle/data/SRE/ai-sre-agent-incidentfox/charts/incidentfox/templates/lark-bot.yaml
grep -A 25 "larkBot:" /Users/anhdungle/data/SRE/ai-sre-agent-incidentfox/charts/incidentfox/values.yaml
```

- [ ] **Step 2: Create `charts/incidentfox/templates/discord-bot.yaml`**

```yaml
{{- if .Values.services.discordBot.enabled }}
{{- if .Values.services.discordBot.serviceAccount.create }}
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{ .Values.services.discordBot.serviceAccount.name | default "discord-bot" }}
  namespace: {{ .Values.namespace }}
---
{{- end }}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: incidentfox-discord-bot
  namespace: {{ .Values.namespace }}
  labels:
    app: incidentfox-discord-bot
spec:
  replicas: {{ .Values.services.discordBot.replicas | default 1 }}
  selector:
    matchLabels:
      app: incidentfox-discord-bot
  template:
    metadata:
      labels:
        app: incidentfox-discord-bot
    spec:
      serviceAccountName: {{ .Values.services.discordBot.serviceAccount.name | default "discord-bot" }}
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        fsGroup: 1000
      imagePullSecrets:
        {{- toYaml .Values.global.imagePullSecrets | nindent 8 }}
      containers:
        - name: discord-bot
          image: "{{ .Values.services.discordBot.image }}"
          imagePullPolicy: {{ .Values.global.imagePullPolicy | default "IfNotPresent" }}
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]
            readOnlyRootFilesystem: false
          ports:
            - containerPort: 8080
              name: http
          env:
            - name: ORCHESTRATOR_URL
              value: {{ printf "http://incidentfox-orchestrator.%s.svc.cluster.local:%d" .Values.namespace (.Values.services.orchestrator.servicePort | int) | quote }}
            - name: CONFIG_SERVICE_URL
              value: {{ required "global.configService.url is required" .Values.global.configService.url | quote }}
            - name: INTERNAL_HTTP_PORT
              value: "8080"
            - name: INCIDENTFOX_ORG_ID
              value: {{ .Values.services.discordBot.orgId | quote }}
            - name: INCIDENTFOX_TEAM_ID
              value: {{ .Values.services.discordBot.teamId | quote }}
            - name: DISCORD_GUILD_ID
              value: {{ .Values.services.discordBot.guildId | quote }}
            {{- if .Values.externalSecrets.contract.discordBot.enabled }}
            - name: DISCORD_BOT_TOKEN
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.externalSecrets.contract.discordBot.secretName | quote }}
                  key: {{ .Values.externalSecrets.contract.discordBot.botTokenKey | quote }}
            - name: DISCORD_APP_ID
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.externalSecrets.contract.discordBot.secretName | quote }}
                  key: {{ .Values.externalSecrets.contract.discordBot.appIdKey | quote }}
            - name: INCIDENTFOX_TEAM_TOKEN
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.externalSecrets.contract.discordBot.secretName | quote }}
                  key: {{ .Values.externalSecrets.contract.discordBot.teamTokenKey | quote }}
            {{- end }}
          resources:
            {{- toYaml .Values.services.discordBot.resources | nindent 12 }}
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
  name: incidentfox-discord-bot
  namespace: {{ .Values.namespace }}
spec:
  selector:
    app: incidentfox-discord-bot
  ports:
    - name: http
      port: 8080
      targetPort: http
{{- end }}
```

- [ ] **Step 3: Append to `values.yaml` `services:` block** (alphabetical: discordBot comes before larkBot)

```yaml
  discordBot:
    enabled: false
    image: "incidentfox/discord-bot:v0.1.0"
    replicas: 1
    guildId: ""
    orgId: ""
    teamId: ""
    serviceAccount:
      create: true
      name: discord-bot
    resources:
      requests:
        cpu: "50m"
        memory: "128Mi"
      limits:
        cpu: "500m"
        memory: "512Mi"
```

- [ ] **Step 4: Append to `values.yaml` `externalSecrets.contract:` block**

```yaml
    discordBot:
      enabled: false
      secretName: incidentfox-discord-bot
      botTokenKey: bot_token
      appIdKey: app_id
      teamTokenKey: team_token
      botTokenRemoteRefKey: incidentfox/prod/discord_bot_token
      appIdRemoteRefKey: incidentfox/prod/discord_app_id
      teamTokenRemoteRefKey: incidentfox/prod/discord_team_token
```

- [ ] **Step 5: Update `templates/external-secrets.yaml`** to render the discord-bot ExternalSecret (mirror lark-bot block)

Open `charts/incidentfox/templates/external-secrets.yaml`, find the `larkBot` block, and add a parallel `discordBot` block right after it:

```yaml
{{- if .Values.externalSecrets.contract.discordBot.enabled }}
---
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: incidentfox-discord-bot
  namespace: {{ .Values.namespace }}
spec:
  refreshInterval: {{ .Values.externalSecrets.refreshInterval | default "1h" }}
  secretStoreRef:
    name: {{ .Values.externalSecrets.secretStoreRef.name }}
    kind: {{ .Values.externalSecrets.secretStoreRef.kind }}
  target:
    name: {{ .Values.externalSecrets.contract.discordBot.secretName }}
  data:
    - secretKey: {{ .Values.externalSecrets.contract.discordBot.botTokenKey }}
      remoteRef:
        key: {{ .Values.externalSecrets.contract.discordBot.botTokenRemoteRefKey }}
    - secretKey: {{ .Values.externalSecrets.contract.discordBot.appIdKey }}
      remoteRef:
        key: {{ .Values.externalSecrets.contract.discordBot.appIdRemoteRefKey }}
    - secretKey: {{ .Values.externalSecrets.contract.discordBot.teamTokenKey }}
      remoteRef:
        key: {{ .Values.externalSecrets.contract.discordBot.teamTokenRemoteRefKey }}
{{- end }}
```

- [ ] **Step 6: Add to `values.pilot.yaml`** (enable for rollout)

```yaml
services:
  discordBot:
    enabled: true
    image: "103002841599.dkr.ecr.us-west-2.amazonaws.com/incidentfox/discord-bot:v0.1.0"
    guildId: "<your-guild-id>"
    orgId: "<your-org-id>"
    teamId: "<your-team-id>"

externalSecrets:
  contract:
    discordBot:
      enabled: true
```

- [ ] **Step 7: Lint**

```bash
cd /Users/anhdungle/data/SRE/ai-sre-agent-incidentfox
helm lint charts/incidentfox -f charts/incidentfox/values.staging.yaml
helm lint charts/incidentfox -f charts/incidentfox/values.prod.yaml
helm lint charts/incidentfox -f charts/incidentfox/values.pilot.yaml
```

Expected: each "1 chart(s) linted, 0 chart(s) failed".

- [ ] **Step 8: Render to verify**

```bash
helm template charts/incidentfox -f charts/incidentfox/values.pilot.yaml --show-only templates/discord-bot.yaml | head -50
```

Expected: valid Kubernetes YAML for ServiceAccount + Deployment + Service.

- [ ] **Step 9: Commit**

```bash
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  add charts/incidentfox/templates/discord-bot.yaml charts/incidentfox/templates/external-secrets.yaml charts/incidentfox/values.yaml charts/incidentfox/values.pilot.yaml
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  commit -m "feat(charts): add discord-bot deployment + values"
```

---

## Task 14: docker-compose.dev.yml entry + Makefile + .env.discord

**Files:**
- Modify: `docker-compose.dev.yml` (add `discord-bot` service block)
- Modify: `Makefile` (add `logs-discord` target)
- Create: `.env.discord` (template, gitignored already via `.env.*`)

- [ ] **Step 1: Append `discord-bot` service to `docker-compose.dev.yml`** (after `lark-bot` block)

```yaml
  # ─────────────────────────────────────────────────────────────────────────────
  # Discord Bot — connects Discord to SRE Agent via orchestrator
  # Requires DISCORD_BOT_TOKEN, DISCORD_APP_ID, DISCORD_GUILD_ID in .env
  # ─────────────────────────────────────────────────────────────────────────────
  discord-bot:
    build:
      context: ./discord-bot
      dockerfile: Dockerfile
    container_name: incidentfox-discord-bot
    restart: unless-stopped
    env_file:
      - .env
    environment:
      - ORCHESTRATOR_URL=http://orchestrator:8070
      - CONFIG_SERVICE_URL=http://config-service:8080
      - INTERNAL_HTTP_PORT=8080
      - INCIDENTFOX_TEAM_TOKEN=${INCIDENTFOX_TEAM_TOKEN:-${ADMIN_TOKEN:-local-admin-token}}
      - INCIDENTFOX_ORG_ID=${INCIDENTFOX_ORG_ID:-local}
      - INCIDENTFOX_TEAM_ID=${INCIDENTFOX_TEAM_ID:-default}
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
    depends_on:
      - orchestrator
      - sre-agent
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    tmpfs:
      - /tmp:rw,noexec,nosuid,size=100m
    mem_limit: 1g
    cpus: 1
    pids_limit: 50
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    networks:
      - app_network
      - default  # external access for Discord Gateway WebSocket
```

Also update the header comment in docker-compose.dev.yml:

```yaml
# Services:
#   postgres, config-service, credential-resolver, envoy, sre-agent,
#   orchestrator, slack-bot, lark-bot, discord-bot, web-ui (http://localhost:3000)
```

- [ ] **Step 2: Add `logs-discord` target to Makefile**

```make
.PHONY: ... logs-discord ...

logs-discord:
	$(DC) -f $(COMPOSE_FILE) logs -f discord-bot
```

(Add `logs-discord` to the `.PHONY` line and add the rule alongside `logs-lark`.)

- [ ] **Step 3: Create `.env.discord` template** (parallel to `.env.lark`)

```bash
ANTHROPIC_API_KEY=

DISCORD_BOT_TOKEN=
DISCORD_APP_ID=
DISCORD_GUILD_ID=

INVESTIGATE_AUTH_TOKEN=local-dev-investigate-token
ORCHESTRATOR_INTERNAL_TOKEN=local-dev-internal-token
INCIDENTFOX_TEAM_TOKEN=local-admin-token
INCIDENTFOX_ORG_ID=local
INCIDENTFOX_TEAM_ID=default

ADMIN_TOKEN=local-admin-token
TOKEN_PEPPER=localdev-pepper-must-be-32-chars-minimum!!
LOG_LEVEL=INFO

SLACK_BOT_TOKEN=xoxb-disabled-placeholder
SLACK_SIGNING_SECRET=disabled-placeholder
```

- [ ] **Step 4: Validate compose**

```bash
docker compose -f docker-compose.dev.yml config --services
```

Expected: includes `discord-bot` in the list (alongside web-ui, lark-bot, etc.)

- [ ] **Step 5: Commit**

```bash
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  add docker-compose.dev.yml Makefile .env.discord
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  commit -m "feat(local): add discord-bot to docker-compose.dev + .env.discord template"
```

(`.env.discord` is excluded from staging by `.gitignore`'s `.env.*` rule, so the commit will only include compose + Makefile. `git add .env.discord` will be a no-op silently — that's fine.)

---

## Task 15: GitHub Actions deploy workflow update

**Files:**
- Modify: `.github/workflows/deploy-eks.yml`

- [ ] **Step 1: Add `discord-bot` to choices list (the `services` input options)**

Find the existing block:
```yaml
          - lark-bot
          - ultimate-rag
```

Insert `discord-bot` (alphabetical):
```yaml
          - discord-bot
          - lark-bot
          - ultimate-rag
```

- [ ] **Step 2: Add `discord-bot` to the build matrix `services:` list**

Find:
```yaml
        service: [agent, config-service, credential-resolver, k8s-gateway, orchestrator, sandbox-router, slack-bot, lark-bot, ultimate-rag, web-ui, ai-pipeline]
```

Insert `discord-bot` (alphabetical, before `k8s-gateway`):
```yaml
        service: [agent, config-service, credential-resolver, discord-bot, k8s-gateway, orchestrator, sandbox-router, slack-bot, lark-bot, ultimate-rag, web-ui, ai-pipeline]
```

- [ ] **Step 3: Add `discord-bot` to the build-matrix `include:` block**

Find the `lark-bot` block and add a parallel `discord-bot` entry:
```yaml
          - service: discord-bot
            context: ./discord-bot
            dockerfile: ./discord-bot/Dockerfile
            image: incidentfox-discord-bot
```

- [ ] **Step 4: Add to restart loop**

Find:
```yaml
            restart_deployment "incidentfox-lark-bot"
          else
```

Replace with:
```yaml
            restart_deployment "incidentfox-lark-bot"
            restart_deployment "incidentfox-discord-bot"
          else
```

- [ ] **Step 5: Add to per-service case in restart switch**

Find:
```yaml
              lark-bot) restart_deployment "incidentfox-lark-bot" ;;
```

Add immediately after:
```yaml
              discord-bot) restart_deployment "incidentfox-discord-bot" ;;
```

- [ ] **Step 6: Add to wait_for_deployment loop**

Find:
```yaml
          wait_for_deployment "incidentfox-lark-bot"
```

Add immediately after:
```yaml
          wait_for_deployment "incidentfox-discord-bot"
```

- [ ] **Step 7: Validate YAML**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/deploy-eks.yml'))"
```

Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  add .github/workflows/deploy-eks.yml
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  commit -m "ci: add discord-bot to deploy-eks.yml"
```

---

## Task 16: User-facing setup doc

**Files:**
- Create: `docs/DISCORD_SETUP.md`
- Modify: `docs/LARK_SETUP.md`, `docs/GOOGLE_CHAT_SETUP.md`, `docs/TEAMS_SETUP.md` (add Discord cross-link)

- [ ] **Step 1: Create `docs/DISCORD_SETUP.md`**

```markdown
# Discord Setup Guide

This guide walks you through adding IncidentFox to your Discord server.

**Time required:** ~5 minutes

**Prerequisites:**
- A Discord server (guild) where you have permission to add bots
- A Discord account with developer access (for first-time app creation)

---

## 1. Create the Discord Application

1. Go to [https://discord.com/developers/applications](https://discord.com/developers/applications)
2. Click **New Application** → name it (e.g., "IncidentFox")
3. In the left sidebar, click **Bot**
4. Click **Reset Token** to generate a bot token. **Save this token** — you'll need it as `DISCORD_BOT_TOKEN`. Discord won't show it again.
5. Under **Privileged Gateway Intents**, enable:
   - **Message Content Intent**
   - **Server Members Intent** (optional, useful for Phase 2)
6. Save changes.
7. From the left sidebar, click **General Information** → copy the **Application ID**. This is `DISCORD_APP_ID`.

## 2. Invite the Bot to Your Server

1. In the left sidebar, click **OAuth2** → **URL Generator**
2. Under **Scopes**, check `bot`
3. Under **Bot Permissions**, check:
   - View Channels
   - Send Messages
   - Embed Links
   - Read Message History
   - Add Reactions
4. Copy the generated URL at the bottom and open it in a new tab
5. Select your Discord server from the dropdown → **Authorize** → solve the captcha

## 3. Get the Server (Guild) ID

1. In Discord, enable Developer Mode: **Settings** → **Advanced** → **Developer Mode**
2. Right-click your server icon → **Copy Server ID**. This is `DISCORD_GUILD_ID`.

## 4. Configure IncidentFox

For self-hosted deployments, set in your environment (or `.env.discord`):

```bash
DISCORD_BOT_TOKEN=<token from step 1.4>
DISCORD_APP_ID=<application id from step 1.7>
DISCORD_GUILD_ID=<guild id from step 3>
```

For SaaS-hosted IncidentFox, your IncidentFox admin handles this.

## 5. Start Using IncidentFox

In any channel where the bot has access, mention it:

```
@IncidentFox why is checkout-service slow?
```

```
@IncidentFox what changed in the last 30 minutes?
```

IncidentFox will reply with a rich embed that updates as the agent investigates. When done, react with 👍 or 👎 to record feedback.

---

## Available Commands

Phase 1 supports natural-language @mentions only. Slash commands (`/investigate`) are planned for Phase 2.

| Trigger | Description |
|---------|-------------|
| `@IncidentFox <question>` | Start an incident investigation |
| 👍 reaction on bot reply | Mark the answer as helpful |
| 👎 reaction on bot reply | Mark the answer as unhelpful |

---

## Connecting Your Tools

IncidentFox needs access to your observability stack to investigate. Connect tools via the IncidentFox web dashboard:

1. Log in to your IncidentFox dashboard
2. Go to **Settings** → **Integrations**
3. Connect Datadog, PagerDuty, AWS, Kubernetes, etc.

See [INTEGRATIONS.md](INTEGRATIONS.md) for details.

---

## Troubleshooting

### Bot doesn't respond when mentioned

1. Verify the bot is in your server (member list shows it as Online)
2. Verify the channel has Send Messages + Embed Links permissions for the bot
3. Check the bot's logs: `kubectl logs deploy/incidentfox-discord-bot -n incidentfox` (or `make logs-discord` locally)
4. Confirm **Message Content Intent** is enabled in the Discord Developer Portal

### Bot replies but embed never updates

The orchestrator may be unreachable. Check `kubectl logs deploy/incidentfox-orchestrator` for errors.

### "Missing Permissions" errors in logs

The bot's role lacks Send Messages, Embed Links, or Add Reactions in that channel. Update channel permissions via Discord channel settings → Permissions.

### Wrong server (bot acts in unintended servers)

The bot is bound to a single `DISCORD_GUILD_ID`. Inviting it to a different server will not enable @mentions there. To support multiple servers, see Phase 2 (multi-guild OAuth).

---

## Next Steps

- [Connect your observability tools](INTEGRATIONS.md)
- [Slack Setup](SLACK_SETUP.md) — Set up IncidentFox in Slack
- [MS Teams Setup](TEAMS_SETUP.md) — Set up IncidentFox in Microsoft Teams
- [Google Chat Setup](GOOGLE_CHAT_SETUP.md) — Set up IncidentFox in Google Chat
- [Lark Setup](LARK_SETUP.md) — Set up IncidentFox in Lark
```

- [ ] **Step 2: Add Discord backlink to `docs/LARK_SETUP.md`** Next Steps section:

Find:
```markdown
- [Google Chat Setup](GOOGLE_CHAT_SETUP.md) — Set up IncidentFox in Google Chat
```

Add right after:
```markdown
- [Discord Setup](DISCORD_SETUP.md) — Set up IncidentFox in Discord
```

- [ ] **Step 3: Add Discord backlink to `docs/GOOGLE_CHAT_SETUP.md`**

Find:
```markdown
- [Lark Setup](LARK_SETUP.md) - Set up IncidentFox in Lark
```

Add right after:
```markdown
- [Discord Setup](DISCORD_SETUP.md) - Set up IncidentFox in Discord
```

- [ ] **Step 4: Add Discord backlink to `docs/TEAMS_SETUP.md`**

Find:
```markdown
- [Lark Setup](LARK_SETUP.md) - Set up IncidentFox in Lark
```

Add right after:
```markdown
- [Discord Setup](DISCORD_SETUP.md) - Set up IncidentFox in Discord
```

- [ ] **Step 5: Commit**

```bash
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  add docs/DISCORD_SETUP.md docs/LARK_SETUP.md docs/GOOGLE_CHAT_SETUP.md docs/TEAMS_SETUP.md
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  commit -m "docs: add DISCORD_SETUP.md and cross-links"
```

---

## Task 17: CLAUDE.md update

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update architecture diagram**

Find:
```
Lark   → lark-bot (long-conn or webhook) ─→ orchestrator ─↗
```

Add right after:
```
Discord → discord-bot (Gateway WebSocket) ─→ orchestrator ─↗
```

Also update the line:
```
config-service ← used by web_ui, slack-bot, lark-bot, orchestrator, credential-resolver
```
to:
```
config-service ← used by web_ui, slack-bot, lark-bot, discord-bot, orchestrator, credential-resolver
```

And:
```
Three entry points for running agents: **Slack** (via slack-bot), **Lark** (via lark-bot, routed through orchestrator), and **web_ui** (directly).
```
to:
```
Four entry points for running agents: **Slack** (via slack-bot), **Lark** (via lark-bot, routed through orchestrator), **Discord** (via discord-bot, routed through orchestrator), and **web_ui** (directly).
```

- [ ] **Step 2: Add discord-bot rows to "Key files" table** (after lark-bot rows):

```markdown
| discord-bot/app.py | Discord service entry, Gateway connection lifecycle |
| discord-bot/gateway_client.py | discord.py Bot wiring (on_message, on_reaction_add) |
| discord-bot/investigation_handler.py | Discord investigation lifecycle (post embed, stream, finalize, add 👍/👎 reactions) |
| discord-bot/feedback_handler.py | 👍/👎 reaction → config-service feedback POST |
```

- [ ] **Step 3: Update "Architecture decisions pending" item #1**

Find:
```markdown
1. **Orchestrator integration**: sre-agent currently bypasses orchestrator and talks directly to slack-bot. lark-bot is the first chat surface routed through orchestrator (Phase 1 single-tenant; Phase 2 adds OAuth multi-tenancy). MS Teams and Google Chat webhook entry points already live in orchestrator but lack streaming. slack-bot remains direct-to-agent for now.
```

Replace with:
```markdown
1. **Orchestrator integration**: sre-agent currently bypasses orchestrator and talks directly to slack-bot. lark-bot was the first chat surface routed through orchestrator (Phase 1 single-tenant; Phase 2 adds OAuth multi-tenancy). discord-bot follows the same orchestrator-routed pattern (Phase 1 single-guild; Phase 2 adds slash commands + multi-guild OAuth). MS Teams and Google Chat webhook entry points already live in orchestrator but lack streaming. slack-bot remains direct-to-agent for now.
```

- [ ] **Step 4: Commit**

```bash
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  add CLAUDE.md
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  commit -m "docs: add discord-bot to CLAUDE.md key files + architecture diagram"
```

---

## Task 18: End-to-end manual verification doc

**Files:**
- Create: `discord-bot/tests/E2E_MANUAL.md`

- [ ] **Step 1: Write manual E2E walkthrough**

```markdown
# Discord Bot E2E Manual Verification

Run after Phase 1 deploy to a pilot cluster (or local docker-compose).

## Prereqs

1. Discord application created per `docs/DISCORD_SETUP.md`
2. Bot invited to a test guild
3. `incidentfox-discord-bot` secret populated in AWS Secrets Manager and synced via ExternalSecret (production), or `.env.discord` filled in (local)
4. `services.discordBot.enabled=true` in pilot values.yaml (production), or `discord-bot` running in docker-compose.dev.yml (local)

## Smoke 1 — Basic @mention investigation

1. Deploy: `helm upgrade --install incidentfox charts/incidentfox -f values.pilot.yaml` (or `make dev` locally)
2. Watch pod logs: `kubectl logs deploy/incidentfox-discord-bot -f` (or `make logs-discord`)
3. Expect: `event: gateway_ready`
4. In a Discord channel where the bot is present, send: `@IncidentFox why is checkout slow?`
5. Within ~3s: a blue embed appears, titled "IncidentFox Investigation", quoting your question
6. Within ~10s: embed updates with streaming partial output
7. Within ~60s: embed turns green ("Investigation Complete") with full result
8. Bot adds 👍 and 👎 reactions to the final embed

## Smoke 2 — Reaction feedback

1. After Smoke 1, click the 👍 reaction on the bot's final embed
2. Check `make logs-discord`: expect `event: feedback_recorded reaction: thumbs_up`
3. Check config-service logs: expect a POST to `/api/v1/feedback` with `session_id`, `user_id`, `reaction: thumbs_up`, `source: discord`
4. Click 👎 on the same message — verify `event: feedback_recorded reaction: thumbs_down`

## Smoke 3 — Failure path

1. Stop sre-agent: `kubectl scale deploy incidentfox-sre-agent --replicas=0` (or `docker compose stop sre-agent`)
2. Mention bot. Expect: embed turns red ("Investigation Failed") within ~30s with "orchestrator unreachable" or similar error
3. Restore: `kubectl scale deploy incidentfox-sre-agent --replicas=1`

## Smoke 4 — Single-guild binding

1. Invite the bot to a SECOND Discord server using the same OAuth URL
2. In the second server, send: `@IncidentFox hello`
3. Expect: bot does NOT respond (single-guild binding via `DISCORD_GUILD_ID`)
4. Check `make logs-discord`: no `posted_status_embed` event for the second guild's message
```

- [ ] **Step 2: Commit**

```bash
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  add discord-bot/tests/E2E_MANUAL.md
git -c user.name="ladung" -c user.email="ledung.is14@gmail.com" \
  commit -m "docs(discord-bot): manual E2E verification walkthrough"
```

---

## Self-Review (run by plan author)

**Spec coverage check** (against `docs/superpowers/specs/2026-04-27-discord-bot-design.md`):

| Spec section | Phase 1 task |
|---|---|
| §2 Architecture: standalone discord-bot/ | Tasks 1-12 |
| §2 Architecture: agent dispatch via orchestrator | Tasks 6 (orchestrator_client) — orchestrator endpoint already exists from lark-bot |
| §3 Components: app, gateway_client, event_router | Tasks 5, 10, 12 |
| §3 Components: investigation_handler, stream_handler | Tasks 7, 9 |
| §3 Components: embed_builder, markdown_utils, state | Tasks 2, 3, 4 |
| §3 Components: orchestrator_client, feedback_handler, healthz | Tasks 6, 8, 11 |
| §4 Data flow: inbound @mention | Tasks 5, 9, 10 |
| §4 Data flow: inbound reaction | Tasks 8, 10 |
| §4 Single-tenant binding via DISCORD_GUILD_ID | Task 5 (guild filter), Task 12 (env validation) |
| §5 Auth & secrets | Task 13 (Helm), Task 1 (env.example) |
| §5 Discord intents (privileged) | Task 10 (gateway_client._intents) |
| §6 Slack/Lark→Discord mapping | Reflected in Tasks 3, 4, 10 |
| §7 Error handling | Tasks 9, 8 (handler-level), Task 4 (truncation) |
| §8 Testing | Each task has TDD steps |
| §9 Phasing — Phase 1 only | This entire plan |
| §10 Local dev | Task 14 |
| §11 Helm/Deployment | Tasks 13, 15 |
| §12 Open risks | MESSAGE_CONTENT intent (Task 16 setup doc), embed limit (Task 4 chunking), reaction ambiguity (Task 8 captures all reactions w/ user_id) |

**Placeholder scan:** No "TBD", "TODO", "implement later". Every code block is concrete; every command shows expected output.

**Type/name consistency check:** Verified across tasks — `DiscordMessageEvent`, `Investigation`, `ConversationState`, `OrchestratorClient.stream_agent`, `ReactionType.{THUMBS_UP, THUMBS_DOWN}`, `InvestigationHandler.handle`, `build_status_embed / build_streaming_embed / build_final_embed / build_error_embed`, `_log` helper signature, `DISCORD_*` env var names — all match between definition site and consumer.

**Scope check:** Phase 1 only. Phases 2 (slash commands, threads, multi-guild OAuth) and 3 (feedback dashboards) are deferred to separate plans.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-27-discord-bot-phase-1.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration with isolation between tasks. Good fit for 18 self-contained TDD tasks.
2. **Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints for review.

Which approach?
