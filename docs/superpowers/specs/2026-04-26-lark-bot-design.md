# lark-bot Design

**Date:** 2026-04-26
**Status:** Draft — pending user review
**Owner:** ledung.is14@gmail.com

## 1. Goals & Non-Goals

### Goal

Add a Lark (international) chat surface for IncidentFox with feature parity to the existing slack-bot, supporting:

- Both **self-hosted single-tenant** and **SaaS multi-tenant** deployments (mirroring slack-bot's `oauth_enabled` toggle pattern).
- Both **webhook** and **long-connection** event delivery modes (Lark's analog to Slack's Events API + Socket Mode).
- Eventual full parity with slack-bot features (cards, modals-via-form-cards, file uploads, slash commands, feedback, onboarding).

### Non-goals (initial release)

- **Feishu (China region)** support — code is structured to support it via env-var-switched API base, but verification and launch are deferred.
- **App Home equivalent (Lark Workplace mini-program)** — Lark has no exact analog; deferred to Phase 4.
- **Internationalization (i18n)** — ship English; structure user-facing strings so future extraction is mechanical.

### Driver

A specific customer requires Lark (international) support to roll out IncidentFox. Phase 1 of this spec satisfies that customer; later phases unlock SaaS multi-tenancy and full parity.

## 2. Architecture

```
Lark Open Platform
   │
   ├─ Webhook events ──→ orchestrator/webhooks/lark_app.py ─┐
   │                       (signature verify, decrypt)      │
   │                                                         ▼
   └─ Long-connection ──→ lark-bot/ (standalone svc) ──→ lark-bot core
                          ws_client.py                  ├─ event_dispatcher
                                                         ├─ card_builder
                                                         ├─ stream_handler
                                                         ├─ multi-tenant routing
                                                         └─ orchestrator client
                                                                │
                                                                ▼
                                                        orchestrator
                                                        AgentApiClient (streaming)
                                                                │
                                                                ▼
                                                          sre-agent (SSE)
```

### Service split

- **New service `lark-bot/`** — standalone Python service. Runs the long-connection WebSocket client to Lark, hosts an internal HTTP endpoint (`/internal/lark/event`) that orchestrator calls when webhook mode is in use. Holds all Lark-specific logic (cards, markdown, file handling, state, onboarding).
- **`orchestrator/webhooks/lark_app.py`** — thin endpoint: signature verification, payload decryption, event normalization, then forwards to lark-bot's internal endpoint. No business logic.
- **All agent dispatch from lark-bot routes through orchestrator's `AgentApiClient`** — strategic-direction-aligned per `CLAUDE.md` ("Long-term, all surfaces should go through orchestrator"). lark-bot does not call sre-agent directly.

### Why standalone over orchestrator-only

Long-connection mode is a stateful WebSocket — it does not fit a stateless webhook router. Co-locating long-connection logic with webhook handling in orchestrator would mix concerns. Standalone also lets Lark-heavy customers scale lark-bot independently.

### Why route through orchestrator vs direct-to-agent

slack-bot's direct-to-agent path is documented as the legacy outlier. Building lark-bot to talk through orchestrator from day one aligns with the strategic direction and reuses orchestrator's existing multi-tenant infrastructure. The cost is one new orchestrator capability: a streaming agent dispatch endpoint (today most webhook integrations are fire-and-forget; only slack-bot streams). This capability also benefits future Teams/Google Chat streaming work.

## 3. Components (inside `lark-bot/`)

| File | Responsibility | Slack analog |
|------|---------------|--------------|
| app.py | Service entry; runs long-connection client + internal HTTP server | slack-bot/app.py |
| ws_client.py | lark-oapi long-connection event dispatcher | (Bolt Socket Mode) |
| http_server.py | Internal endpoint for orchestrator-forwarded webhook events | (n/a — Bolt handles) |
| event_router.py | Normalizes events from both transports → unified handler | (Bolt's ack model) |
| installation_store.py | Multi-tenant install records, backed by config-service | slack-bot/installation_store.py |
| oauth_handler.py | Lark Store App OAuth install/uninstall flow | (Bolt OAuth) |
| config_client.py | Per-tenant config loader (config-service) | slack-bot/config_client.py |
| orchestrator_client.py | Calls orchestrator's streaming agent endpoint, consumes SSE | (slack-bot calls sre-agent directly) |
| investigation_handler.py | Investigation lifecycle: dispatch, stream, render, finalize | slack-bot/investigation_handler.py |
| stream_handler.py | SSE → progressive Lark card edits | slack-bot/stream_handler.py |
| card_builder.py | Lark interactive card composition (card v2 schema) | slack-bot/message_builder.py |
| markdown_utils.py | Convert agent markdown → Lark card md_v2 subset | slack-bot/markdown_utils.py |
| table_converter.py | Tables → Lark card columns | slack-bot/table_converter.py |
| file_handler.py | Lark file upload/download (`im/v1/files`, `im/v1/images`) | slack-bot/file_handler.py |
| onboarding.py | Form-card-based onboarding | slack-bot/onboarding.py |
| setup_handler.py | Form-card-based setup/config flows | slack-bot/setup_handler.py |
| modal_builder.py | Lark form cards (modal-equivalent) | slack-bot/modal_builder.py |
| modal_handler.py | Form card callback handlers | slack-bot/modal_handler.py |
| state.py | Per-conversation in-memory state | slack-bot/state.py |
| model_catalog.py | Model picker | slack-bot/model_catalog.py |
| assets/, assets_config.py, asset_manager.py | Logo, images | matching slack-bot |
| k8s/ + chart template | Deployment manifests | matching slack-bot |
| Dockerfile, pyproject.toml, README.md, env.example, lark-manifest.json | Infra/config | matching |

## 4. Data Flow

### Inbound event (long-connection mode)

1. `ws_client` receives event from Lark over WebSocket.
2. Verify `event_id` (de-dup window), extract `tenant_key`, `chat_id`, `message_id`, `root_id` (thread).
3. `event_router` → `installation_store` lookup by `tenant_key` → resolve IncidentFox `org_id`/`team_id`.
4. `config_client` loads effective per-team config (org→team merge from config-service).
5. `investigation_handler` creates session, calls `orchestrator_client.dispatch_streaming(...)`.
6. SSE events stream back from orchestrator → `stream_handler` edits the in-flight Lark card progressively (`im/v1/messages` PATCH).
7. Final result rendered as a card; feedback action buttons attached.

### Inbound event (webhook mode)

1. Lark posts event to orchestrator `/webhooks/lark`.
2. `orchestrator/webhooks/lark_app.py` verifies Lark signature, decrypts payload (Lark's optional `Encrypt Key` AES encryption).
3. Normalized payload POSTed to lark-bot's `/internal/lark/event`.
4. Same as long-connection from step 2.

### Multi-tenant routing key

Lark's `tenant_key` is the org-unique tenant identifier in every event payload. It is stored in `installation_store` and mapped to IncidentFox `org_id`/`team_id`. Per-team feature config lives under the `lark.*` namespace in config-service.

## 5. Authentication & Secrets

| Secret | Use | Where |
|--------|-----|-------|
| `LARK_APP_ID`, `LARK_APP_SECRET` | Lark API auth (single-tenant self-hosted, or Store App credentials) | env / values.yaml |
| `LARK_VERIFICATION_TOKEN` | Webhook signature verification | env / values.yaml |
| `LARK_ENCRYPT_KEY` | Webhook payload AES decryption (optional per Lark app config) | env / values.yaml |
| Per-install `tenant_access_token` | Per-tenant API calls (multi-tenant SaaS); refreshed via `tenant_access_token/internal` endpoint | installation_store record in config-service DB, encrypted at rest using config-service's existing token-encryption mechanism |
| `LARK_OAUTH_ENABLED` | Toggle single vs multi-tenant mode (mirrors slack-bot's `oauth_enabled`) | env |
| `LARK_TRANSPORT_MODE` | `long_connection` / `webhook` / `hybrid` | env |
| `LARK_API_BASE` | Default `https://open.larksuite.com` (Lark intl); overridable for Feishu | env |
| `LARK_BASE_URL` | Public OAuth redirect base for SaaS distribution | env |

All secrets routed via AWS Secrets Manager → ExternalSecrets → K8s Secret. Outbound Lark API calls go through credential-proxy (Envoy) so the sandbox boundary holds.

## 6. Slack → Lark Concept Mapping

| Slack | Lark | Notes |
|-------|------|-------|
| Workspace | Tenant (`tenant_key`) | 1:1 |
| Channel | Chat (`chat_id`) | 1:1 |
| Thread | Reply chain (`root_id`) | Lark threads are flatter; we use `root_id` to scope investigations |
| Block Kit | Card v2 | Distinct schema; need a separate builder |
| Modal | Form card | Lark form cards (introduced 2023) cover modal use cases |
| App Home | Workplace mini-program | Deferred to Phase 4; no exact analog |
| Socket Mode | Long-connection mode | Both stateful WebSocket |
| `chat.update` | `im/v1/messages/{id}` PATCH | Used for progressive card updates |
| Bolt SDK | `lark-oapi` SDK | Official Python SDK |
| Slack markdown | `md_v2` subset inside cards | Different escapes; no `<@user>`/`<#chan>` syntax — use Lark `<at user_id="...">` instead |

## 7. Error Handling

- Standard `{"success": bool, "result": ..., "error": "..."}` for internal service-to-service calls.
- Lark API rate limits: respect `X-Ogw-Ratelimit-*` headers; exponential backoff in `orchestrator_client` and outbound card edits.
- Stream timeouts: mirror PR #501 pattern (SSE timeouts in slack-bot).
- Long-connection disconnect: auto-reconnect with backoff (`lark-oapi` handles; we log and emit metrics).
- Webhook decryption failure: 401 from orchestrator endpoint, log and drop event.
- Tenant not installed (multi-tenant SaaS only): respond with onboarding prompt card. In single-tenant self-hosted mode this case cannot occur — `tenant_key` is fixed and bound at boot.
- Unknown event type: log at INFO, ack with no-op.

## 8. Testing

- **Unit tests** for: `card_builder`, `markdown_utils`, `table_converter`, signature verification (`verify_lark_signature`), payload decryption (`decrypt_lark_payload`), `installation_store`, `event_router` normalization.
- **Integration tests** for: `orchestrator_client` (mock orchestrator SSE), `stream_handler` (assert sequence of card edits given an event stream).
- **E2E tests** under `lark-bot/tests/`: `lark-oapi` mock event dispatch → assert end-to-end card output. Mirrors `slack-bot/tests` structure.

## 9. Phasing

Even with "full parity" as the destination, the work ships in independent phases:

- **Phase 1 — MVP for first customer.** Webhook + long-connection event handling. @mention and DM. Agent dispatch via orchestrator with SSE streaming. Basic card rendering with progressive updates. Single-tenant config (`LARK_OAUTH_ENABLED=false`). Helm chart, secrets wiring, Dockerfile, env.example.
- **Phase 2 — SaaS multi-tenancy.** Lark Store App OAuth flow. `installation_store` backed by config-service. First-time-install onboarding form cards (welcome, integration linking). Per-install `tenant_access_token` lifecycle (refresh, revocation).
- **Phase 3 — Feature parity.** Ongoing setup/configuration form cards (Slack-modal equivalents — edit team config, add integrations, change models). File upload/download. Slash commands. Feedback reactions. Model picker.
- **Phase 4 — Post-parity.** Workplace mini-program (App Home equivalent). Feishu region support. i18n string extraction.

Each phase ships independently and is shippable on its own. The first customer gets Phase 1 quickly; SaaS multi-tenant rolls with Phase 2.

## 10. Orchestrator Changes

- `orchestrator/webhooks/lark_app.py` — new webhook endpoint: signature verify, decrypt, forward to lark-bot internal endpoint.
- `orchestrator/webhooks/signatures.py` — add `verify_lark_signature` (HMAC over `timestamp + nonce + encrypted_body` per Lark spec) and `decrypt_lark_payload` (AES-CBC with `Encrypt Key`).
- `orchestrator/webhooks/router.py` — wire `/webhooks/lark` route + Lark URL verification challenge handling (Lark sends a `url_verification` event with a `challenge` field on app config; endpoint must echo `{"challenge": <value>}`).
- `orchestrator/clients.py` — extend `AgentApiClient` with a streaming dispatch variant (used by lark-bot), or introduce `AgentStreamingClient`. This capability is reusable by future Teams/Google Chat streaming work.
- Orchestrator chart/values: pass `LARK_*` env vars where needed.

## 11. Helm / Deployment

- `charts/incidentfox/templates/lark-bot.yaml` — new Deployment + Service (mirror `slack-bot.yaml`).
- Values keys: `larkBot.enabled`, `larkBot.image.tag`, `larkBot.replicas`, `larkBot.transportMode`, `larkBot.oauthEnabled`, `larkBot.apiBase`, `larkBot.baseUrl`.
- ExternalSecret for Lark credentials (per-env).
- Disabled by default in staging/prod values; enabled in pilot/customer values for the rollout.
- `.github/workflows/deploy-eks.yml` — add `lark-bot` to the services list and image build matrix.
- ECR repo: `103002841599.dkr.ecr.us-west-2.amazonaws.com/incidentfox/lark-bot`.

## 12. Open Questions / Risks

- **Streaming through orchestrator.** Today orchestrator's agent dispatch is mostly fire-and-forget for webhook integrations (Teams/Google Chat post a final result; only slack-bot streams, and it bypasses orchestrator). Adding a streaming endpoint is a non-trivial change. Decision: ship streaming in Phase 1. Fallback if customer timeline forces otherwise: ship "dispatch + final result only" first, retrofit streaming as Phase 1.5 before Phase 2 starts.
- **`tenant_access_token` refresh semantics.** Lark tokens are short-lived (~2h). The refresh strategy needs to handle bursty incident traffic without thundering-herd refreshing. Plan: cache with 5-min refresh-ahead; mutex per tenant.
- **Card update rate limits.** Lark rate-limits per-bot card edits. Stream handler must throttle (debounce ~250ms) to avoid 429s under fast token streaming.
- **Lark-oapi SDK maturity.** The official Python SDK is younger than slack_bolt; some surfaces (long-connection mode) are newer. Build a thin adapter so we can swap to raw HTTP if a critical bug blocks us.
