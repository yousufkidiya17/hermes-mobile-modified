---
name: hermes-vm-telegram-deploy
description: "Deploy Hermes + Telegram bot on a GCP VM with free models."
version: 1.0.0
author: Hermes Agent
tags: [GCP, VM, Hermes, Telegram, gateway, LocalBridge, systemd, SSH-windows]
---

# Deploy Hermes Agent on GCP VM with Telegram

Set up a full Hermes Agent installation on a GCP VM including Telegram bot integration, LocalBridge proxy (OpenCode free models), gateway with cron, and multi-model aliases. 24/7 operation via systemd.

## Full Architecture

```
GCP VM (hermes-vibe-coder, e2-small, us-east1-b)
├── Hermes Agent (v0.19+)
│   ├── Telegram bot (@Pri17bot) ← 24/7 polling
│   ├── Gateway (systemd user service)
│   ├── Cron scheduler (built-in)
│   └── 320+ skills synced
├── LocalBridge (server.mjs :4000)
│   └── OpenCode Zen API → 7 free models
└── SSH from Windows (space-in-username workaround)
```

## Prerequisites

- GCP account with billing/quota
- gcloud CLI installed (`gcloud.cmd` on Windows)
- Telegram bot token (from @BotFather)
- OpenCode CLI installed locally (for the LocalBridge config)

## Step 1 — Create VM

```bash
# Check zones with capacity
gcloud compute instances create hermes-vm-name \
  --zone us-east1-b \                    # Avoid us-central1 (capacity issues)
  --machine-type e2-small \              # ~$7/mo, enough for Hermes+Telegram
  --image-family ubuntu-2404-lts-amd64 \
  --image-project ubuntu-os-cloud \
  --boot-disk-size 20GB \
  --tags hermes-vm
```

**Pitfall:** us-central1-a/b often show `ZONE_RESOURCE_POOL_EXHAUSTED` for e2-small. Try us-east1-b or us-west1-a.

## Step 2 — SSH from Windows (Critical Workaround)

Windows username with a space (e.g. "Mohd yousuf") breaks gcloud's SSH config. The IdentityFile path in `~/.ssh/config` is unquoted.

**Fix — skip the broken config entirely:**
```bash
ssh -F /dev/null \
  -o StrictHostKeyChecking=no \
  -i "C:/Users/Your Name/.ssh/google_compute_engine" \
  user@<VM-IP>
# User is the gcloud account username (kidiyayousuf17), not the Windows username
```

**Pattern for running commands:**
```bash
ssh -F /dev/null -o StrictHostKeyChecking=no \
  -i "C:/Users/Your Name/.ssh/google_compute_engine" \
  user@<VM-IP> 'command here'
```

## Step 3 — Install Hermes on VM

```bash
# Install deps first (one SSH command)
ssh -F /dev/null ... user@<IP> 'sudo apt update && sudo apt install -y curl'

# Install Hermes
ssh -F /dev/null ... user@<IP> \
  'curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash'

# Add to PATH
ssh -F /dev/null ... user@<IP> \
  'export PATH=$PATH:/home/<user>/.local/bin'
```

## Step 4 — Set Up LocalBridge (DeepSeek/Mimo Free Models)

```bash
# Copy server.mjs to VM
scp -F /dev/null -i "key" "C:/path/to/server.mjs" user@<IP>:~/LocalBridge/

# Install deps on VM
ssh -F /dev/null ... user@<IP> \
  'cd ~/LocalBridge && npm init -y && npm install express turndown htmlparser2'

# Find the right server.mjs — the one with web search/fetch endpoints
# Usually under OneDrive/Desktop/Hermes_Setup_Files/LocalBridge/server.mjs

# Start LocalBridge
ssh -F /dev/null ... user@<IP> \
  'cd ~/LocalBridge && nohup node server.mjs > server.log 2>&1 &'

# Verify
curl -s http://localhost:4000/health
# Expected: {"status":"ok","service":"Aetherix Proxy Gateway","models":7,...}
```

## Step 5 — Configure Hermes

Write config.yaml to `~/.hermes/config.yaml`:

```yaml
model:
  default: opencode/mimo-v2.5-free
  provider: custom
  api_key: aetherix-master-7x9k2m4p
  base_url: http://localhost:4000/v1
  reasoning_effort: ultra

display:
  show_reasoning: false
  streaming: true
  tool_progress: all

gateway:
  enabled: true
  platforms:
    telegram:
      enabled: true

model_aliases:
  deepseek:
    model: opencode/deepseek-v4-flash-free
    provider: custom
    base_url: http://localhost:4000/v1
    api_key: aetherix-master-7x9k2m4p
  mimo:
    model: opencode/mimo-v2.5-free
    provider: custom
    base_url: http://localhost:4000/v1
    api_key: aetherix-master-7x9k2m4p
  nemotron:
    model: opencode/nemotron-3-ultra-free
    provider: custom
    base_url: http://localhost:4000/v1
    api_key: aetherix-master-7x9k2m4p
```

Add Telegram token to `~/.hermes/.env`:
```
TELEGRAM_BOT_TOKEN=your_token_here
GATEWAY_ALLOW_ALL_USERS=true
```

## Step 6 — Install Gateway

```bash
export PATH=$PATH:/home/<user>/.local/bin
hermes gateway install
systemctl --user status hermes-gateway
```

Gateway starts automatically. Enable linger so it survives logout:
```bash
loginctl enable-linger <user>
```

## Step 7 — Model Selection on Telegram

User can switch models via Telegram using `/model <alias>` command (e.g. `/model deepseek`, `/model mimo`). Requires `model_aliases` section in config.yaml.

## Troubleshooting

### Telegram Adapter Issues

| Problem | Symptom | Fix |
|---------|---------|-----|
| **Polling stuck** | "Connecting to Telegram (attempt 1/8)" — never progresses | Check webhook conflict, delete webhook via API |
| **Webhook conflict** | "can't use getUpdates while webhook is active" | Delete webhook: `curl -s "https://api.telegram.org/bot<TOKEN>/deleteWebhook?drop_pending_updates=true"` |
| **Network reset** | `httpx.ReadError:` periodic disconnects | Normal for long-polling; gateway auto-reconnects |
| **Send failed** | `send_path_degraded` | Temporary network issue, auto-retries |
| **MOA errors** | "No LLM provider configured for task=moa_aggregator" | Disable MOA: add `moa: enabled: false` to config.yaml |
| **Config overwritten** | model changed to moonshotai/tokenrouter | Someone ran `hermes setup` or similar. Rewrite config.yaml manually. |

### Gateway Management

```bash
# Status
systemctl --user status hermes-gateway

# Restart cleanly (kills old PIDs first)
systemctl --user stop hermes-gateway
kill -9 $(pgrep -f "python.*gateway")
systemctl --user reset-failed hermes-gateway
systemctl --user start hermes-gateway

# Or via hermes CLI
hermes gateway restart

# View logs
journalctl --user -u hermes-gateway -n 50 --no-pager

# Reinstall service definition
hermes gateway install
```

### Config Protect Against Overwrite

After setting config.yaml, the gateway or `hermes setup` may overwrite it. Common triggers:
- Running `hermes setup` interactively
- Gateway startup with incompatible config_version
- User testing other providers (tokenrouter, etc.)

**Fix:** Always keep a backup of the working config.

## User Preferences

- Language: Hinglish (Hindi-Urdu mix)
- Tone: Casual, direct, fast — no verbose explanations
- Prefers comparison tables with emojis over paragraphs
- Values practical hands-on execution over theory
- Frustrated by long debugging loops — give quick status, ask for direction
- Wants visual feedback (tables, diagrams, progress bars)
