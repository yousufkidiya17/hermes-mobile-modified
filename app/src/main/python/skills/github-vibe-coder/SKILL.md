---
name: github-vibe-coder
description: "Automate daily GitHub contributions via Hermes cron."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [GitHub, automation, cron, vibe-coding, PR, Telegram]
    related_skills: [github-pr-workflow, github-issues, hermes-agent]
---

# GitHub Vibe Coder — Automated Daily Contribution Agent

Use Hermes as orchestrator to automate daily GitHub contributions: find trending repos, work good-first-issues, submit PRs, and report via Telegram.

## When to Use
- User wants consistent daily GitHub activity (green profile)
- Building an automated "vibe coding" pipeline
- Automating OSS contributions via cron + AI agents

## Architecture

```
Hermes (orchestrator) — 24/7 VPS
  ├── Daily cron → trending repos check
  ├── gh CLI → good-first-issues search
  ├── OpenHands/OpenCode → code + PR
  ├── Hermes memory → track what's done
  └── Telegram → daily report + checkpoint
```

## Prerequisites

- Hermes running 24/7 (VPS recommended — DigitalOcean/Hetzner ~$5/mo)
- `gh` CLI installed + authenticated (`gh auth login`)
- Telegram gateway configured in Hermes
- GitHub token with repo scope

## Step 1: GitHub CLI Setup

```bash
gh auth login           # Personal Access Token or OAuth
gh auth status          # Verify
```

## Step 2: Hermes Cron Job

```bash
hermes cron add \
  --name "github-daily" \
  --schedule "0 8 * * *" \
  --prompt "
    1. Check GitHub trending for Python/JS/TS repos
    2. Find good-first-issues with gh CLI
    3. Pick one issue matching your skills
    4. Fork the repo, write fix, submit PR
    5. Log to Hermes memory so you don't repeat
    6. Send summary via Telegram
  " \
  --deliver telegram
```

## Step 3: Trending Discovery via Hermes

Hermes can scrape `github.com/trending` or use GitHub search:

```bash
gh search issues --label "good-first-issue" \
  --limit 10 \
  --sort created \
  --json repositoryUrl,title,url
```

## Step 4: Fork + Fix Flow

```bash
gh repo fork OWNER/REPO --clone
cd REPO
# AI writes fix code here
git add -A && git commit -m "fix: description"
git push origin main
gh pr create --title "Fix: ..." --body "Closes #N"
```

## Step 5: Human Checkpoint (Recommended)

Before PR submit, Hermes sends a Telegram approval request:
```
🔍 Found issue: pandas#12345 — typo in docs
   Fix ready. Approve PR submit? (yes/no)
```

## Step 6: Memory & Tracking

```bash
hermes memory add target=memory \
  content="PR #123 submitted to pandas/docs — awaiting review"
```

## Optional: Fork Sync Cron

Prevent stale forks with a daily sync cron:
```bash
cd repos/* && git fetch upstream && git merge upstream/main
```

## Pitfalls
- Maintainers review slowly — don't expect daily PR merges
- GitHub rate limits API calls (5,000/hr authenticated)
- Rejected PRs happen — document why in memory
- gh CLI needs Git credentials configured
- Test PRs on your own repos first before contributing to others
