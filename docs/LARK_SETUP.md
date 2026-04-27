# Lark Setup Guide

This guide walks you through adding IncidentFox to your Lark (international) workspace.

**Time required:** ~2 minutes

**Prerequisites:**
- Lark (international) workspace with admin or normal-user permissions to add apps
- Access to a chat where your team handles incidents

> **Note:** This guide covers Lark international (`larksuite.com`). Feishu (China region, `feishu.cn`) is not yet supported.

---

## 1. Install IncidentFox

### Option A: Search in Lark App Directory

1. Open **Lark** (desktop, mobile, or `larksuite.com`)
2. Open **Workplace** in the left sidebar
3. Click **App Directory** (or **Search apps**)
4. Search for **"IncidentFox"**
5. Click **Add** → **Add to organization** (admins) or **Add for me** (individuals)

### Option B: Direct Link

Your workspace admin may provide a direct install link. Click it and follow the prompts to add IncidentFox.

### Option C: Admin Installation (Organization-wide)

Lark admins can install IncidentFox for the entire organization:

1. Go to **Lark Admin Console** (`admin.larksuite.com`)
2. Navigate to **Workplace** → **App Management**
3. Click **Add app** → Search for **"IncidentFox"**
4. Choose visibility (everyone or specific departments / groups)
5. Click **Enable** → **Confirm**

---

## 2. Add to a Chat

Once installed, add IncidentFox to a group chat where your team handles incidents:

1. Open the group chat in Lark
2. Click the chat name at the top → **Settings** → **Group Bots** → **Add Bot**
3. Search for **"IncidentFox"** → Click **Add**

Or simply type `@IncidentFox` in any group and follow the prompt to add it.

For 1-on-1 conversations, just open a direct chat with **IncidentFox** from the App Directory and start sending messages — no @-mention needed.

---

## 3. Start Using IncidentFox

Mention IncidentFox in any group chat to start an investigation:

```
@IncidentFox why is checkout-service returning 500 errors?
```

```
@IncidentFox what changed in the last 30 minutes?
```

```
@IncidentFox check the health of the payment-api deployment
```

In a 1-on-1 chat with the bot, omit the `@IncidentFox` and just type your question.

IncidentFox will analyze your connected observability tools (Datadog, PagerDuty, AWS, Kubernetes, etc.) and respond with actionable insights via an interactive Lark card that updates in real time.

---

## 4. Available Commands

| Command | Description |
|---------|-------------|
| `@IncidentFox investigate <issue>` | Start an incident investigation |
| `@IncidentFox status <service>` | Check the status of a service |
| `@IncidentFox help` | Show available commands |

---

## Connecting Your Tools

IncidentFox needs access to your observability stack to investigate incidents. Connect your tools through the IncidentFox web dashboard:

1. Log in to your IncidentFox dashboard
2. Go to **Settings** → **Integrations**
3. Connect your tools (Datadog, PagerDuty, AWS, Kubernetes, Grafana, etc.)

See [INTEGRATIONS.md](INTEGRATIONS.md) for detailed setup instructions.

---

## Troubleshooting

### IncidentFox not responding

1. Make sure the bot is added to the group (check **Settings** → **Group Bots**)
2. Verify you're using `@IncidentFox` to mention the bot in group chats
3. Contact your workspace admin to confirm the app is approved for your organization

### "App not available" or app cannot be added

Your Lark admin may need to approve IncidentFox. Ask your admin to:

1. Go to **Lark Admin Console** → **Workplace** → **App Management**
2. Find IncidentFox and approve / enable it for your organization
3. Verify the app's permission scopes are accepted

### Messages not being processed

If IncidentFox acknowledges your message but doesn't return results, your observability tools may not be connected. Check your IncidentFox dashboard under **Settings** → **Integrations**.

### Card stuck on "Investigating…"

The investigation card edits in place as the agent works. If it stays on the initial blue "Investigating…" state for more than ~2 minutes, the agent may be unreachable. Check the IncidentFox status page or contact support.

### Wrong region (Feishu instead of Lark)

This integration is currently for Lark international (`larksuite.com`) only. Feishu (`feishu.cn`) accounts are not supported at this time — please contact support if you need Feishu integration.

---

## Next Steps

- [Connect your observability tools](INTEGRATIONS.md)
- [Slack Setup](SLACK_SETUP.md) — Set up IncidentFox in Slack
- [MS Teams Setup](TEAMS_SETUP.md) — Set up IncidentFox in Microsoft Teams
- [Google Chat Setup](GOOGLE_CHAT_SETUP.md) — Set up IncidentFox in Google Chat
- [Discord Setup](DISCORD_SETUP.md) — Set up IncidentFox in Discord
