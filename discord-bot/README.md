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
