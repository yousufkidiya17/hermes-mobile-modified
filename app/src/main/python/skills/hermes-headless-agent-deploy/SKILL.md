---
name: hermes-headless-agent-deploy
description: "Deploy Hermes on a headless VM with Telegram + free models."
version: 1.0.0
author: Hermes Agent
tags: [deployment, GCP, VM, Hermes, Telegram, free-models, headless, 24-7]
---

# Hermes Headless Agent Deploy

Deploy Hermes Agent as a 24/7 headless autonomous agent on a cloud VM with:
- **Telegram bot** for user interaction
- **LocalBridge proxy** for free AI models (DeepSeek, Mimo, Nemotron via OpenCode)
- **Cron scheduler** for autonomous tasks
- **systemd service** for auto-restart

The VM runs independently — no dependency on the user's local Hermes.

## Architecture

```
Cloud VM (Ubuntu 24.04)
  ├── Hermes Agent (systemd)
  │   ├── Gateway ─── Telegram bot
  │   ├── Cron scheduler
  │   ├── 7 free model aliases
  │   └── reasoning_effort: ultra
  └── LocalBridge (:4000)
      ├── /v1/chat/completions → Free models
      ├── /v1/web/search → DuckDuckGo Lite
      └── /v1/web/fetch → Any URL
```

## Prerequisites

- Cloud VM (e2-micro minimum, e2-small recommended, Ubuntu 24.04)
- Telegram bot token from @BotFather
- OpenCode Zen API free models

## Step 1: Create VM

```bash
gcloud compute instances create hermes-agent \
  --zone us-east1-b \
  --machine-type e2-small \
  --image-family ubuntu-2404-lts-amd64 \
  --image-project ubuntu-os-cloud \
  --boot-disk-size 20GB
```

Zone fallbacks: `us-west1-a`, `europe-west1-b`, `us-central1-f`.

## Step 2: SSH (Windows Space in Username)

```bash
ssh -F /dev/null -o StrictHostKeyChecking=no \
  -i "C:/Users/Your Name/.ssh/google_compute_engine" \
  user@<VM_IP>
```

## Step 3: Install Hermes

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
echo 'export PATH=$PATH:$HOME/.local/bin' >> ~/.bashrc
source ~/.bashrc
hermes --version
```

## Step 4: Deploy LocalBridge

On VM: `mkdir -p ~/LocalBridge && cd ~/LocalBridge && npm init -y && npm install express turndown htmlparser2`

Copy `server.mjs` from local machine via scp, then start:
```bash
cd ~/LocalBridge && nohup node server.mjs > server.log 2>&1 &
curl -s http://localhost:4000/health
```

## Step 5: Configure Hermes

Write `~/.hermes/config.yaml`:
- model.default: `opencode/mimo-v2.5-free`
- provider: `custom`, base_url: `http://localhost:4000/v1`
- api_key: `aetherix-master-7x9k2m4p`
- reasoning_effort: `ultra`
- gateway.platforms.telegram.enabled: true
- model_aliases for deepseek, mimo, nemotron (each with same base_url/key)

## Step 6: Telegram Bot

```bash
echo "TELEGRAM_BOT_TOKEN=<token>" >> ~/.hermes/.env
echo "GATEWAY_ALLOW_ALL_USERS=true" >> ~/.hermes/.env
hermes gateway install
systemctl --user start hermes-gateway
```

User sends first message to bot to pair.

## Step 7: Cron Jobs

```bash
hermes cron create --name "daily-check" --schedule "0 8 * * *" \
  --prompt "Check trending repos and report." --deliver telegram
```

## Troubleshooting

**Telegram stuck on "attempt 1/8":** Clear old sessions:
```bash
curl "https://api.telegram.org/bot<TOKEN>/deleteWebhook?drop_pending_updates=true"
systemctl --user restart hermes-gateway
```

**Systemd reset loop:**
```bash
systemctl --user reset-failed hermes-gateway
sudo kill -9 $(pgrep -f "hermes.*gateway" | head -1)
systemctl --user restart hermes-gateway
```

**Config overwritten:** After gateway migration, verify model.default and base_url.

**User preferences:** Hinglish, casual, concise. **CRITICAL: Always explain the plan first, then ask permission before acting.** The user corrected the agent multiple times in Session 2026-07-29: must describe → ask → wait for approval → execute. Never jump into actions without the user saying yes.

> **Reference:** `references/gcp-vm-setup-tricks.md` — Node.js fetch vs curl on GCP, systemd user services, GitHub device-code auth, Telegram adapter stuck-on-attempt-1/8 fix, config overwrite recovery.
