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
