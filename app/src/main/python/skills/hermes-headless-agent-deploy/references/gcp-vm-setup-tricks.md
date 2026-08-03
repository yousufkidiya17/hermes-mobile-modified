# GCP VM Setup Tricks from Session 2026-07-29

## Node.js v18 Native fetch vs curl on GCP

Node.js v18's native `fetch()` sends different headers than curl to DuckDuckGo Lite
(`https://lite.duckduckgo.com/lite/`), causing DDG to return a shorter HTML page
(~14KB) **without** `class="result-link"` elements (empty results).

Curl gets the full page (~24KB) with results.

**Fix:** Use `child_process.execSync()` to run curl from Node.js:
```js
const { execSync } = await import('child_process');
const html = execSync(`curl -sL 'https://lite.duckduckgo.com/lite/' -H 'User-Agent: Mozilla/5.0' -X POST -d 'q=${encodeURIComponent(query)}'`, { timeout: 15000 }).toString();
```

Alternative: Use regex-based parsing (works with both single and double quotes):
```js
const linkRe = /<a[^>]+class=['"]result-link['"][^>]*>([^<]+)<\/a>/gi;
```

**htmlparser2 note:** The ESM-only package requires dynamic import. Single-quoted
HTML attributes (`class='result-link'`) are parsed correctly by htmlparser2 —
`attribs.class` contains the string without quotes.

## Systemd User Services for Node.js

To make Node.js processes persist after SSH logout, use **user-level systemd services**
(not system-level with sudo).

```ini
# ~/.config/systemd/user/localbridge.service
[Unit]
Description=LocalBridge Proxy
After=network.target

[Service]
ExecStart=/usr/bin/node /home/user/LocalBridge/server.mjs
Restart=always
RestartSec=5
WorkingDirectory=/home/user/LocalBridge

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now localbridge
systemctl --user is-active localbridge  # verify
```

**Key:** Must use `systemctl --user` (not sudo). Linger must be enabled for
processes to survive logout: `loginctl enable-linger <user>`.

**Port conflict:** If a foreground `node server.mjs` is already running, the
systemd service fails to bind. Kill the manual process first:
`kill $(ps aux | grep -v grep | grep "node.*server" | awk '{print $2}')`

## GitHub CLI auth in Headless/Container Environments

`gh auth login` opens a browser — use device code flow:

```bash
gh auth login --hostname github.com --scopes "repo,read:org,gist"
# Output: "First copy your one-time code: XXXX-XXXX"
# User opens https://github.com/login/device and enters the code.
```

Or use `GH_TOKEN` environment variable with a pre-generated PAT.

## Telegram adapter Stuck on "attempt 1/8"

The Hermes Gateway Telegram adapter (`python-telegram-bot` + httpx) on GCP
occasionally gets `httpx.ReadError` and can't complete the initial long-poll.

**Fix sequence:**
```bash
# 1. Clear Telegram server state
curl "https://api.telegram.org/bot<TOKEN>/deleteWebhook?drop_pending_updates=true"

# 2. Kill all gateway processes
kill $(ps aux | grep -v grep | grep "hermes.*gateway" | head -1)
systemctl --user reset-failed hermes-gateway

# 3. Restart
systemctl --user restart hermes-gateway
```

The `send_path_degraded` error means the adapter lost both send and receive paths.
Direct API calls via curl always work — the issue is specifically the python-telegram-bot
long-poll adapter.

## Config File Gets Overwritten

After a gateway migration or update, the `model.default` and `base_url` in
`~/.hermes/config.yaml` may revert to `moonshotai/kimi-k3-free` and
`https://api.tokenrouter.com/v1`. Always verify and fix back to the local
LocalBridge endpoint if this happens.
