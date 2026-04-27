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
