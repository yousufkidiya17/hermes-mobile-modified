---
name: vibe-coder-vm-setup
description: "Set up auto GitHub contribution worker on GCP VMs."
version: 1.0.0
author: Hermes Agent
tags: [GCP, VM, GitHub, vibe-coder, automation, cron, systemd]
---

# 🌊 Vibe Coder VM Setup — GCP VM Automation

Automate daily GitHub contributions by setting up a vibe coder worker on a GCP VM that uses the Aetherix Proxy (LocalBridge) for AI-powered issue analysis.

## Architecture

```
User's Local Machine (Hermes Cron)
  └── Triggers reminder/setup via cron
      
GCP VM (aetherix-proxy-v2)
  ├── OpenCode serve (:3333) → AI backend
  ├── Aetherix Proxy (:4000) → OpenAI-compatible API
  ├── vibe-ai-worker.py → AI-powered issue analysis & forking
  ├── vibe-daily.sh → Shell-based issue discovery
  ├── gh CLI → GitHub operations
  └── systemd timer → Daily execution
```

## Prerequisites

- GCP VM with SSH access (gcloud compute ssh or direct SSH key)
- OpenCode serve or similar AI backend running on the VM
- Aetherix Proxy Gateway (or any OpenAI-compatible proxy on localhost:4000)
- Node.js, Python 3, pip

## Step 1: Install Prerequisites on VM

```bash
# Git
sudo apt-get update && sudo apt-get install -y git

# GitHub CLI
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
echo 'deb [signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main' | sudo tee /etc/apt/sources.list.d/github-cli.list
sudo apt-get update && sudo apt-get install -y gh

# Python deps
sudo apt-get install -y python3-requests jq

# Git config
git config --global user.name "Your Name"
git config --global user.email "your@email.com"
git config --global init.defaultBranch main
```

## Step 2: Create Vibe Coder Workspace

```bash
mkdir -p ~/vibe-coder/{scripts,repos,logs}
```

## Step 3: Deploy Scripts

Place these files in `~/vibe-coder/scripts/`:

### vibe-ai-worker.py
AI-powered worker that:
1. Searches good-first-issues via gh CLI
2. Analyzes issues using Aetherix Proxy (DeepSeek)
3. Forks repos
4. Logs everything

### vibe-daily.sh
Shell-based alternative that uses gh CLI directly.

### gh-auth.sh
Helper to authenticate gh CLI with a token.

### status.sh
Check all service statuses.

## Step 4: Set gh Auth

```bash
# Get token from https://github.com/settings/tokens (scope: repo, workflow)
cd ~/vibe-coder
bash scripts/gh-auth.sh <your-token>
```

## Step 5: Systemd Timer

```bash
# Service
sudo tee /etc/systemd/system/vibe-coder.service > /dev/null << 'SERVICE'
[Unit]
Description=🌊 Vibe Coder AI — Daily GitHub Contribution Agent
After=network.target opencode.service aetherix-proxy.service
Requires=opencode.service aetherix-proxy.service

[Service]
Type=oneshot
User=kidiyayousuf17
WorkingDirectory=/home/kidiyayousuf17/vibe-coder
ExecStart=/home/kidiyayousuf17/vibe-coder/scripts/vibe-ai-worker.py
StandardOutput=append:/home/kidiyayousuf17/vibe-coder/logs/systemd.log
StandardError=append:/home/kidiyayousuf17/vibe-coder/logs/systemd.log

[Install]
WantedBy=multi-user.target
SERVICE

# Timer (daily)
sudo tee /etc/systemd/system/vibe-coder.timer > /dev/null << 'TIMER'
[Unit]
Description=🌊 Vibe Coder Daily Timer
Requires=vibe-coder.service

[Timer]
OnCalendar=daily
Persistent=true
RandomizedDelaySec=3600

[Install]
WantedBy=timers.target
TIMER

sudo systemctl daemon-reload
sudo systemctl enable vibe-coder.timer
sudo systemctl start vibe-coder.timer
```

## Verify

```bash
systemctl list-timers --no-pager | grep vibe
# Should show: vibe-coder.timer ... 7h left

sudo journalctl -u vibe-coder.service -n 20
```

## Next Steps / ADK Multi-Agent

For the full ADK (Agent Development Kit) multi-agent setup:
1. Install Google ADK on the VM
2. Create specialized sub-agents (issue finder, code writer, PR submitter)
3. Orchestrate via Hermes delegate_task or direct Python orchestration

## Pitfalls

- gh CLI must be authenticated before the timer runs
- Debian 12 has PEP 668 — use `apt install python3-requests` not pip
- SSH from Windows git-bash needs quoted paths for gcloud.cmd
- The AI worker depends on the Aetherix Proxy being up (which depends on OpenCode serve)
- jq is required for the shell-based daily script (vibe-daily.sh)
