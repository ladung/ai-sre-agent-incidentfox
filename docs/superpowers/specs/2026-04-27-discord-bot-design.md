# discord-bot Design

**Date:** 2026-04-27
**Status:** Draft — pending user review
**Owner:** ledung.is14@gmail.com

## 1. Goals & Non-Goals

### Goal

Add a Discord chat surface for the internal SRE team. The bot connects to one Discord guild, listens for @mentions in channels, dispatches investigations via orchestrator with SSE streaming, replies as a progressively-updated rich embed, and captures 👍/👎 reaction feedback on the final result.

### Non-goals (Phase 1)

- Multi-guild / multi-tenant support — bot is bound to a single `DISCORD_GUILD_ID` at boot
- Slash commands, message components (buttons), file uploads
- OAuth installation flow — bot is invited via a one-time manual OAuth URL
- Public Discord App Directory listing
- Voice / stage channels — not relevant for SRE triage

### Driver

The internal SRE team uses Discord. They want IncidentFox available without leaving Discord, mirroring how slack-bot and lark-bot serve their respective surfaces.

## 2. Architecture

```
Discord Gateway (WebSocket)
   │
   └─ on_message ──→ discord-bot/ (standalone svc) ──→ orchestrator
                                                          (dispatch-stream)
                                                              │
                                                              ▼
                                                          sre-agent (SSE)
   │
   └─ on_reaction_add ──→ discord-bot/ ──→ config-service (feedback log)
```

### Service split

- **New service `discord-bot/`** — standalone Python service. Single-process, async, runs `discord.py`'s `commands.Bot` event loop. Connects to Discord's Gateway over WebSocket.
- **No HTTP server is needed for inbound** — Discord delivers everything (messages, reactions, presence updates) over the Gateway. There is no webhook entry point. A small aiohttp `/healthz` endpoint runs on an internal port for K8s liveness/readiness probes.
- **All agent dispatch routes through orchestrator's `/api/v1/agents/dispatch-stream`** — strategic-direction-aligned per `CLAUDE.md`. discord-bot does not call sre-agent directly.

### Why standalone over orchestrator-only

The Discord Gateway is a stateful WebSocket: a long-lived outbound connection with heartbeats, sequence numbers, and resume tokens. It does not fit a stateless webhook router. This matches the same architectural decision made for lark-bot (long-connection mode) and slack-bot (Socket Mode).

### Why route through orchestrator vs direct-to-agent

The strategic direction in `CLAUDE.md` is "all surfaces should go through orchestrator". slack-bot's direct path is the legacy outlier; lark-bot was the first surface routed through orchestrator. discord-bot follows that established pattern.

## 3. Components (inside `discord-bot/`)

| File | Responsibility | Lark-bot analog |
|------|---------------|-----------------|
| `app.py` | Service entry, env validation, lifecycle | `lark-bot/app.py` |
| `gateway_client.py` | `discord.py` bot setup, on_message + on_reaction_add hooks | `lark-bot/ws_client.py` |
| `event_router.py` | Normalize Discord events, mention detection, filter own messages | `lark-bot/event_router.py` |
| `investigation_handler.py` | Lifecycle: post initial embed → stream → finalize → add reactions | `lark-bot/investigation_handler.py` |
| `stream_handler.py` | SSE → debounced embed edits | `lark-bot/stream_handler.py` |
| `embed_builder.py` | Discord rich-embed composition (status / streaming / final / error) | `lark-bot/card_builder.py` |
| `markdown_utils.py` | Agent markdown → Discord markdown subset, chunking for 4096-char description limit | `lark-bot/markdown_utils.py` |
| `orchestrator_client.py` | SSE consumer for orchestrator's dispatch-stream endpoint | `lark-bot/orchestrator_client.py` |
| `feedback_handler.py` | 👍/👎 reaction handler → config-service feedback POST | (new) |
| `state.py` | In-memory `bot_message_id → Investigation` mapping for reaction lookup | `lark-bot/state.py` |
| `healthz.py` | Tiny aiohttp `/healthz` endpoint for K8s probes | (subset of `http_server.py`) |
| `pyproject.toml`, `Dockerfile`, `README.md`, `env.example`, `.gitignore` | Service infrastructure | matching |
| `tests/` | Pytest TDD tests | matching |

Files we explicitly do **not** need (vs lark-bot):

- `lark_api.py` equivalent — `discord.py` itself is the API client
- `http_server.py` for inbound webhooks — Discord has no inbound webhook for messages, only Gateway
- Signature verification — Gateway uses bot token directly in the WebSocket handshake, no per-request HMAC
- Decryption — Discord does not encrypt event payloads

## 4. Data Flow

### Inbound @mention

1. Discord Gateway fires `on_message` event in `discord.py`
2. Filters: ignore non-mentions of the bot, ignore the bot's own messages, optionally ignore messages from outside the bound `DISCORD_GUILD_ID`
3. `event_router.normalize_event()` extracts: `guild_id`, `channel_id`, `message_id`, `author_id`, `content` (with bot mention stripped), thread context (if any)
4. `investigation_handler` posts initial blue embed via `message.reply(embed=...)`, captures the bot's reply message ID
5. `state.put(session_id, Investigation(bot_message_id=..., status="running"))`
6. Calls `orchestrator_client.stream_agent(message=prompt, session_id=session_id, tenant_id=org_id, team_id=team_id)`
7. SSE events stream back → `stream_handler.handle_stream` (debounced 250 ms) → `bot_message.edit(embed=...)` updates the embed in place
8. On final event: green embed (success) or red embed (failure)
9. Bot adds 👍 and 👎 reactions to the final message: `await bot_message.add_reaction("👍")` then `await bot_message.add_reaction("👎")`

### Inbound reaction (feedback)

1. Discord Gateway fires `on_reaction_add`
2. Filters: ignore reactions on messages not authored by the bot, ignore the bot's own reactions (Discord includes bot self-reactions in this event), ignore emojis other than 👍 (`\U0001F44D`) and 👎 (`\U0001F44E`)
3. `feedback_handler` resolves: user, message_id → original investigation `session_id` (via `state`)
4. POST to config-service feedback endpoint with payload: `{session_id, user_id, reaction: "thumbs_up"|"thumbs_down", source: "discord", timestamp}`. The endpoint is `POST /api/v1/feedback` (Phase 1 of this spec adds it to config-service if it does not already exist; if config-service has no feedback endpoint yet, the implementation plan will specify either adding it or logging structured JSON to stdout pending a Phase 3 dashboard).

### Session ID

Generated from `channel_id + message_id`, sanitized for K8s RFC 1123 like lark-bot's `generate_session_id`. Format: `discord-<channel>-<message>`, ≤ 63 chars.

## 5. Authentication & Secrets

| Secret | Use | Where |
|--------|-----|-------|
| `DISCORD_BOT_TOKEN` | Gateway connection auth | env / K8s Secret |
| `DISCORD_APP_ID` | Bot identity (used in invite URL generation) | env |
| `DISCORD_GUILD_ID` | Single-tenant binding — bot only acts in this guild | env |
| `INCIDENTFOX_TEAM_TOKEN` | Bearer token for orchestrator + config-service | env / K8s Secret |
| `INCIDENTFOX_ORG_ID`, `INCIDENTFOX_TEAM_ID` | Tenant identity in IncidentFox config-service | env |
| `ORCHESTRATOR_URL` | Where to dispatch investigations | env (`http://orchestrator:8070`) |
| `CONFIG_SERVICE_URL` | Where to log feedback | env (`http://config-service:8080`) |

**No credential-proxy pass-through.** `discord.py` opens its own WebSocket directly to `gateway.discord.gg`; the bot token is sent in the WebSocket handshake. Discord's API design does not allow injecting an Authorization header at a proxy boundary the way Anthropic and Coralogix do. The token does live in env, which is a slight deviation from the credential-proxy pattern. Containment is via:

- K8s Secret with strict RBAC
- Non-root container user (UID 1000)
- Restricted egress (only `gateway.discord.gg`, `discord.com`, orchestrator, config-service)

### Required Discord intents

Set in the Discord Developer Portal AND in `gateway_client.py`:

- `MESSAGE_CONTENT` (privileged — must enable in Developer Portal)
- `GUILDS`
- `GUILD_MESSAGES`
- `GUILD_MESSAGE_REACTIONS`

For a bot in 100+ guilds, Discord requires application review for `MESSAGE_CONTENT`. Single-guild internal use bypasses this gate.

## 6. Slack / Lark → Discord concept mapping

| Slack / Lark concept | Discord equivalent |
|---|---|
| Card / Block Kit | Rich Embed |
| Lark `lark_md` | Discord markdown (basically GitHub-flavored, simpler than Slack mrkdwn) |
| `chat.update` / `im/v1/messages` PATCH | `message.edit(embed=...)` |
| Workspace / tenant | Guild (`guild_id`) |
| Channel | Channel (`channel_id`) |
| Thread | Thread (`thread_id`) — Discord threads are first-class |
| Mention syntax | `<@USER_ID>` raw, `discord.py` provides clean APIs |
| Socket Mode / Long-connection | Gateway (always WebSocket; Discord has no other realtime mode) |
| App Home | (no equivalent — Discord has no per-user "home" UI for bots) |

## 7. Error Handling

- **Gateway disconnect**: discord.py auto-reconnects with exponential backoff. Log only.
- **Rate limits**: Discord enforces per-route rate limits via response headers. discord.py handles transparently.
- **Embed too long**: chunk at 4000 chars (safety margin under the 4096 hard limit), post follow-up messages for overflow. Continuation embeds carry a "(continued)" footer.
- **Stream timeout / orchestrator unreachable**: red embed with the exception message, mirrors lark-bot's pattern.
- **Reaction on stale message**: if the message's `session_id` is no longer in `state` (e.g., bot restarted between investigation and reaction), log at INFO and ignore. Do not crash.
- **Bot lacks send / embed / react permission in a channel**: catch `discord.Forbidden`, send a plain-text reply explaining the missing permission. Do not crash.
- **Unknown event type**: discord.py raises events for everything; we only register handlers for `on_message` and `on_reaction_add`. Other events are silently ignored.

## 8. Testing

- **Unit tests** (TDD style, pytest):
  - `embed_builder` — status / streaming / final / error embed shape, color, title, chunking
  - `markdown_utils` — Discord markdown chunking at 4000 chars, paragraph boundary preservation
  - `event_router` — mention extraction with various Discord mention formats (`<@id>`, `<@!id>`, `<@&role>`)
  - `state` — put / get / clear, thread-safety
  - `feedback_handler` — emoji filter, session resolution, config-service POST shape
- **Integration tests**:
  - `orchestrator_client` with `respx` HTTP mocks — same shape as lark-bot's
  - `stream_handler` with stub callbacks — debounce behavior
  - `investigation_handler` with a `FakeBot` Protocol-typed fake — full lifecycle including reaction add
- **Smoke test**: `app.py` env validation — required vars, transport mode, single-tenant binding
- **Mocking the Discord SDK**: `discord.py` is hard to spin up in-process. Use a thin `Protocol`-typed abstraction so unit tests do not depend on `discord.Client`. The real discord.py wiring lives only in `gateway_client.py`, kept minimal.

## 9. Phasing

- **Phase 1 (this plan)** — @mention trigger → streaming embed → finalize. 👍 / 👎 reactions captured to config-service. Single guild bound at boot. Helm chart, Dockerfile, env.example, tests, docker-compose.dev.yml entry, Makefile target.
- **Phase 2** (separate plan) — slash commands (`/investigate`), threads with multi-turn memory, file uploads, multi-guild OAuth installation flow, multi-tenant routing.
- **Phase 3** — feedback dashboards in web-ui (visualize 👍/👎 trends per agent / per skill), integration with orchestrator's audit logging.

Each phase ships independently and is shippable on its own. Phase 1 covers the internal team's needs; Phases 2-3 are exploratory.

## 10. Local dev

- Add `discord-bot` service to `docker-compose.dev.yml`, mirroring lark-bot's block:
  - `env_file: .env`
  - `depends_on: [orchestrator, sre-agent]`
  - Standard security_opt / cap_drop / tmpfs
  - No port mapping needed (Gateway is outbound; healthcheck is internal)
- New `.env.discord` template with required env vars
- Makefile: add `logs-discord` target

For real local testing, the developer creates a Discord app at discord.com/developers, generates a bot token, copies it to `.env.discord`, and invites the bot to a test guild using a one-time OAuth URL. `app.py` prints the invite URL at boot if the bot has not yet been added to a guild.

## 11. Helm / Deployment

- New `charts/incidentfox/templates/discord-bot.yaml` (mirror `lark-bot.yaml`)
- Values: `services.discordBot.{enabled, image, replicas, guildId}` and `externalSecrets.contract.discordBot`
- Disabled by default in `values.yaml`; enabled in `values.pilot.yaml` for the internal-team rollout
- `.github/workflows/deploy-eks.yml` — add `discord-bot` to choices list, image build matrix, deploy steps

## 12. Open Risks

- **`MESSAGE_CONTENT` is a privileged intent.** For bots in 100+ guilds, Discord requires application review. Single-guild internal use case bypasses this.
- **Embed character limit (4096 chars).** Long agent answers fan out to multiple follow-up messages. UX could feel chunky on a really long investigation. Mitigation: post a "Full output:" link to a paste service if available, or rely on the `discord-bot` thread (Phase 2 enhancement).
- **Reaction-as-feedback ambiguity.** Anyone in the channel can react, not just the original asker. Phase 1 captures all reactions and tags them with `user_id`; Phase 2 can filter to just the asker if signal noise becomes a problem.
- **discord.py 2.x vs alternatives.** discord.py was archived briefly in 2021 then revived under Rapptz. It is active again. Alternative: `pycord` (a fork that continued during the archive period). We choose discord.py since it is the original and has the broadest documentation. We can swap to pycord later if maintenance becomes a concern — the Protocol-typed boundaries in our code keep this swap cheap.
- **Token-in-env deviation from credential-proxy pattern.** `DISCORD_BOT_TOKEN` lives in the discord-bot container's env (unlike Anthropic / Coralogix which are injected by Envoy). Discord's design does not support a proxy boundary. Mitigation is K8s Secret + RBAC + restricted egress + non-root container user.
