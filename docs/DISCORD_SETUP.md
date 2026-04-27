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
