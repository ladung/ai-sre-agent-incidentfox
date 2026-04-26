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
