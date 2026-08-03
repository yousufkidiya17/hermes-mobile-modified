---
name: aetherix-proxy-gateway
description: "Set up a local OpenAI-compatible proxy with fast web tools."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [proxy, openai-compatible, localbridge, express, web-search, web-fetch, hermes-config]
    related_skills: [hermes-agent, mcp-market]
---

# Aetherix Proxy Gateway

A Node.js Express proxy that bridges Hermes Agent to any OpenAI-compatible API (OpenCode Zen API, Ollama, vLLM, etc.). Supports streaming, tool calling, and custom endpoints for web search and web fetch.

## Architecture

```
Hermes Agent → LocalBridge (:4000) → OpenCode Zen API (or any OpenAI-compatible endpoint)
                              ↓
                 Web Search (DuckDuckGo Lite)
                 Web Fetch (Direct HTTP → Markdown/Text)
```

## When to Use
- User wants to connect Hermes to free/alternative models
- User complains about slow browser-based search (CAPTCHA blocks, 30+ sec delays)
- User needs fast web search + fetch that bypasses browser rendering
- Setting up a local proxy for Hermes custom provider

## Key Files
- `C:\LocalBridge\server.mjs` — Main Express server
- `Hermes config.yaml` — `model.provider: custom`, `base_url: http://localhost:4000/v1`

## Setup

### Prerequisites
```bash
# Node.js + npm/yarn required
npm install express turndown htmlparser2
```

### Basic Server (Chat Completions + Models)
```javascript
// server.mjs — minimal
import express from "express";
const app = express();
app.use(express.json({ limit: "10mb" }));

app.post("/v1/chat/completions", async (req, res) => {
  const response = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Authorization": "Bearer YOUR_KEY" },
    body: JSON.stringify(req.body)
  });
  const data = await response.json();
  res.json(data);
});

app.get("/v1/models", (req, res) => {
  res.json({ object: "list", data: models });
});

app.listen(4000);
```

### Hermes Config
```yaml
model:
  default: opencode/deepseek-v4-flash-free
  provider: custom
  api_key: your-api-key
  base_url: http://localhost:4000/v1
```

### Custom Provider Profile
Hermes needs a `custom_provider_init.py` with `supports_vision=True`, `default_max_tokens=65536`, and aliases for ollama/local/vllm/llamacpp.

## Adding Fast Web Search + Fetch

### Installation
```bash
npm install turndown htmlparser2
```

### Web Fetch Endpoint
```javascript
import TurndownService from "turndown";

async function fetchUrlContent(url, format = "markdown") {
  const controller = new AbortController();
  setTimeout(() => controller.abort(), 30000);

  const res = await fetch(url, {
    headers: {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      "Accept-Language": "en-US,en;q=0.9",
    },
    signal: controller.signal,
  });

  let output = await res.text();
  if (output.length > 5 * 1024 * 1024) throw new Error("Response too large (>5MB)");

  if (format === "markdown" && res.headers.get("content-type")?.includes("html")) {
    output = new TurndownService().turndown(output);
  }

  return { url, contentType: res.headers.get("content-type") || "", format, output };
}
```

### ⚠️ Web Search Endpoint — DuckDuckGo Lite (with Node-fetch fix)

**CRITICAL:** Node.js v18's native `fetch()` to DuckDuckGo Lite returns a different/blocked HTML page than curl does. The htmlparser2 parser receives HTML without any `result-link` elements, producing empty results despite the query succeeding from curl.

**Fix: Use `curl` via `child_process.execSync` instead of `fetch()` for the DuckDuckGo call.**

```javascript
// POST /v1/web/search — DuckDuckGo Lite via curl (fixes Node-fetch DDG issue)
const { execSync } = await import("child_process");

const curlCmd = `curl -sL 'https://lite.duckduckgo.com/lite/' \\
  -H 'User-Agent: Mozilla/5.0' \\
  -X POST -d 'q=${encodeURIComponent(query)}'`;

const html = execSync(curlCmd, { timeout: 15000, maxBuffer: 1024 * 1024 }).toString();

// Parse with regex (more reliable than htmlparser2 for DDG's mixed quote styles)
const linkRe = /<a[^>]+rel=['"]nofollow['"][^>]+href=['"]([^'"]+)['"][^>]*class=['"]result-link['"][^>]*>([^<]+)<\/a>/gi;
const snipRe = /<td class=['"]result-snippet['"]>([\s\S]*?)<\/td>/gi;
const links = [...html.matchAll(linkRe)];
const snips = [...html.matchAll(snipRe)];
const results = [];

for (let i = 0; i < links.length; i++) {
  results.push({
    title: links[i][2].trim(),
    url: links[i][1],
    snippet: snips[i] ? snips[i][1].replace(/<[^>]*>/g, "").trim().substring(0, 300) : "",
  });
}

res.json({ results });
```

**Why Node.js fetch fails:** DuckDuckGo serves different content depending on the HTTP client's advertised capabilities (TLS/HTTP version, `sec-*` headers). Node.js native `fetch` (undici) sends headers that trigger a simplified/landing page. Curl sends a more browser-like signal and gets full search results.

If sticking with `htmlparser2` instead of regex, use `.includes()` not `===` for class matching — DDG mixes single and double quotes in attributes:
```javascript
// WRONG: attribs.class === "result-link"  — fails on single-quote versions
// RIGHT:
if (name === "a" && attribs.class?.includes("result-link")) { ... }
```

## Deploying on GCP VM

### Creating a New VM (with zone resource exhaustion fallback)
```bash
# If e2-small not available in us-central1-a, try other zones/regions:
gcloud compute instances create hermes-vibe-coder \
  --zone us-east1-b \                    # ← try different zone
  --machine-type e2-small \
  --image-family ubuntu-2404-lts-amd64 \
  --image-project ubuntu-os-cloud \
  --boot-disk-size 20GB \
  --tags hermes-vm
```

### SSH from Windows (space-in-username workaround)
The Windows username "Mohd yousuf" breaks gcloud compute ssh inline commands. Use direct SSH with `-F /dev/null`:
```bash
ssh -F /dev/null -o StrictHostKeyChecking=no \
  -i "C:/Users/Mohd yousuf/.ssh/google_compute_engine" \
  kidiyayousuf17@<VM_IP> "command"
```
⚠️ Never use `pgrep -f hermes` in SSH commands — it matches the SSH command text and kills the connection.

### Copying server.mjs to VM
```bash
scp -F /dev/null -o StrictHostKeyChecking=no \
  -i "C:/Users/Mohd yousuf/.ssh/google_compute_engine" \
  "server.mjs" \
  kidiyayousuf17@<VM_IP>:~/LocalBridge/
```

### Starting LocalBridge on VM
```bash
cd ~/LocalBridge && npm init -y && npm install express turndown htmlparser2
nohup node server.mjs > server.log 2>&1 &
```
Or better, use systemd to persist after SSH logout:

#### LocalBridge systemd Service
`~/.config/systemd/user/localbridge.service`:
```ini
[Unit]
Description=Aetherix LocalBridge Proxy
After=network.target

[Service]
ExecStart=/usr/bin/node /home/username/LocalBridge/server.mjs
Restart=always
RestartSec=5
WorkingDirectory=/home/username/LocalBridge

[Install]
WantedBy=default.target
```
```bash
systemctl --user daemon-reload
systemctl --user enable --now localbridge
systemctl --user status localbridge
```
⚠️ Ensure no other process is holding port 4000 before starting (kill stale node processes).
⚠️ Run `loginctl enable-linger $USER` so the user service survives SSH logout.

### Hermes Gateway

### Install Hermes
```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
source ~/.bashrc
```

### Config: Multiple Models with Aliases
Support **7 free models** via OpenCode Zen API, all with `reasoning_effort: ultra`:
```yaml
model:
  default: opencode/mimo-v2.5-free
  provider: custom
  api_key: aetherix-master-7x9k2m4p
  base_url: http://localhost:4000/v1
  reasoning_effort: ultra

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
  ling:
    model: opencode/ling-3.0-flash-free
    provider: custom
    base_url: http://localhost:4000/v1
    api_key: aetherix-master-7x9k2m4p
```

Switch models via `/model deepseek`, `/model mimo`, `/model nemotron` etc.

### Hermes Gateway (Telegram + Cron)
```bash
# Install gateway service
hermes gateway install

# Configure Telegram in ~/.hermes/.env
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_HOME_CHANNEL=user_chat_id

# Allow all users (testing only)
GATEWAY_ALLOW_ALL_USERS=true
```

### ⚠️ Gateway Pitfalls

#### Config Gets Overwritten
If the user runs scripts with a different API (e.g., tokenrouter.com), the `config.yaml` will be overwritten with that API's settings. Always restore:
```yaml
default: opencode/mimo-v2.5-free
provider: custom
api_key: aetherix-master-7x9k2m4p
base_url: http://localhost:4000/v1
```

#### MOA (Mixture of Agents) Error
The gateway may fail with `"No LLM provider configured for task=moa_aggregator provider=openrouter"`. Disable MOA:
```yaml
moa:
  enabled: false
agent:
  model: opencode/mimo-v2.5-free
  provider: custom
```

#### Telegram Adapter Stuck on "Connecting (attempt 1/8)"
The built-in Telegram adapter may hang on long-poll initialization (httpx.ReadError). Workarounds:
1. **Reset polling session:** `curl -s "https://api.telegram.org/bot<TOKEN>/deleteWebhook?drop_pending_updates=true"`
2. **Direct API send works:** Even if polling is stuck, `curl -s "https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<ID>&text=..."` always works
3. **Kill stale PIDs:** Check `ps aux | grep "[g]ateway"` and kill old PIDs before restarting

#### PID Management
Old gateway processes often persist and block new ones. Clean restart:
```bash
systemctl --user stop hermes-gateway
kill -9 $(ps aux | grep "python" | grep -v grep | awk '{print $2}')
systemctl --user reset-failed hermes-gateway
systemctl --user restart hermes-gateway
```

### Gateway Reinstall
If the gateway unit is corrupted or repeatedly failing:
```bash
systemctl --user stop hermes-gateway
hermes gateway install   # reinstalls service definition
systemctl --user reset-failed hermes-gateway
systemctl --user restart hermes-gateway
```

## Pitfalls
- **Space in Windows username** (`Mohd yousuf`) causes path issues in bash — use `-F /dev/null` flag to bypass SSH config, quote IdentityFile paths, or use MSYS2 `/c/Users/...` format
- **Server restart needed** after file changes — kill old process, start new one
- **DuckDuckGo Lite HTML structure may change** — if results are empty, inspect the actual HTML and update CSS class names in the parser. Current classes: `result-link` for links, `result-snippet` for descriptions
- **TurndownService** creates a new instance per call — avoid sharing state
- **Timeout handling** — always set AbortController for fetch calls (30s fetch, 15s search)
- **OpenCode Zen API** may change model names — keep `MODELS` array synced
- **Never use `pgrep -f hermes` in SSH commands** — it matches the SSH command text itself and kills the SSH session
- **Empty projects on GCP** — always check before deleting: `gcloud compute instances list --project=<PROJECT_ID>`
- **Zone resource exhaustion** — if e2-small is unavailable, try a different zone or region (us-central1-a/b/c, us-east1-b)

## Hermes Mobile App → Full Agent Connection
    
The Hermes Mobile Android app (`com.m57.hermescontrol`, F-Droid `com.mobilefork.hermesagent`) connects to the **Hermes Gateway REST API**, not directly to LocalBridge. Connecting to LocalBridge:4000 gives only chat (no skills/tools).

For full agent access on mobile, connect the app to the Gateway URL (not LocalBridge). See `references/hermes-mobile-connection.md` for source code details, connection profiles, and customization.

## Making Hermes Mobile a Standalone Agent

See `references/hermes-mobile-mod-agent.md` for the full plan to turn the Hermes Mobile app into a standalone AI agent using:

- **libtermux-android** — embed a Linux runtime inside the app (Python, Node.js, Bash)
- **MCP (Model Context Protocol)** — keep existing Python tools via an MCP server instead of rewriting in Kotlin
- **LocalBridge** — same Node.js proxy as desktop, runs inside the app via libtermux
- **Android SDK** — direct access to SMS, Call, Camera, Contacts (no Termux:API needed)

## Verification
```bash
# Test health
curl http://localhost:4000/health

# Test web search (JSON)
curl -X POST http://localhost:4000/v1/web/search \
  -H "Content-Type: application/json" \
  -d '{"query":"test query"}'

# Test web fetch (Markdown)
curl -X POST http://localhost:4000/v1/web/fetch \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com","format":"markdown"}'

# Test web fetch (Text)
curl -X POST http://localhost:4000/v1/web/fetch \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com","format":"text"}'
```
