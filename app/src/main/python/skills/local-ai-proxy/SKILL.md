---
name: local-ai-proxy
description: "Bridge Hermes to any model via a Node.js OpenAI proxy."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [proxy, local-ai, bridge, openai-compatible, model-routing]
    related_skills: [opencode, hermes-agent]
---

# Local AI Proxy Bridge

Set up a Node.js Express server as an OpenAI-compatible API proxy that bridges Hermes (or any OpenAI client) to remote/free AI models. Pattern: client → Express proxy → backend model API.

## When to Use
- User wants to use free/remote models (OpenCode Zen API, Ollama, vLLM, etc.) with Hermes
- User needs to add custom endpoints (web search, web fetch) to their AI proxy
- User wants to run a model proxy on a VM for 24/7 access
- User wants to bypass CAPTCHA blocks by using direct HTTP fetch instead of browser

## Architecture

```
Hermes Agent (AI client)
    ↓
Express Proxy (:4000)
    ├── /v1/chat/completions  → Backend model API
    ├── /v1/web/search        → DuckDuckGo Lite (fast, no CAPTCHA)
    ├── /v1/web/fetch         → Direct HTTP fetch + HTML→Markdown
    ├── /v1/models            → List available models
    └── /health               → Health check
```

## Steps

### Step 1: Create Express Server
```javascript
import express from "express";
import TurndownService from "turndown";
import * as htmlparser2 from "htmlparser2";

const app = express();
const PROXY_PORT = 4000;

// CORS
app.use((req, res, next) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization");
  if (req.method === "OPTIONS") return res.sendStatus(204);
  next();
});
```

### Step 2: Chat Completions (Model Passthrough)
Map model IDs to backend IDs, forward messages/tools/streaming:

```javascript
const ZEN_BASE = "https://opencode.ai/zen/v1";
const MODELS = [
  { id: "opencode/deepseek-v4-flash-free", zenId: "deepseek-v4-flash-free" },
  { id: "opencode/mimo-v2.5-free", zenId: "mimo-v2.5-free" },
];

app.post("/v1/chat/completions", async (req, res) => {
  const { model, messages, stream, tools } = req.body;
  const modelEntry = MODELS.find(m => m.id === model);
  const zenModel = modelEntry ? modelEntry.zenId : model;
  const zenRes = await fetch(`${ZEN_BASE}/chat/completions`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model: zenModel, messages, stream, tools }),
  });
  if (stream) { /* SSE pipe */ } else { res.json(await zenRes.json()); }
});
```

### Step 3: Web Search (Fast, No Browser)
```javascript
app.post("/v1/web/search", async (req, res) => {
  const { query } = req.body;
  const html = await fetch("https://lite.duckduckgo.com/lite/", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: `q=${encodeURIComponent(query)}`,
  }).then(r => r.text());

  const results = [];
  let current = null;
  const parser = new htmlparser2.Parser({
    onopentag(name, attribs) {
      if (name === "a" && attribs.class?.includes("result-link"))
        current = { url: attribs.href || "", title: "", snippet: "" };
    },
    ontext(text) {
      if (!current) return;
      const t = text.trim();
      if (!t) return;
      if (!current.title) current.title = t;
      else current.snippet = (current.snippet || "") + t + " ";
    },
    onclosetag(name) {
      if (name === "a" && current && current.title) {
        results.push({ ...current });
        current = null;
      }
    },
  });
  parser.write(html);
  parser.end();
  res.json({ results });
});
```

### Step 4: Web Fetch (URL → Markdown)
```javascript
app.post("/v1/web/fetch", async (req, res) => {
  const { url, format = "markdown" } = req.body;
  const resp = await fetch(url, {
    headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" },
  });
  const html = await resp.text();
  let output = html;
  if (format === "markdown") {
    const turndownService = new TurndownService();
    output = turndownService.turndown(html);
  }
  res.json({ url, contentType: resp.headers.get("content-type"), format, output });
});
```

### Step 5: Auth Middleware (Optional)
```javascript
const API_KEYS = { "your-api-key": { name: "Master Key", active: true } };
app.use("/v1", (req, res, next) => {
  const token = (req.headers.authorization || "").replace("Bearer ", "").trim();
  if (!token || !API_KEYS[token] || !API_KEYS[token].active)
    return res.status(401).json({ error: { message: "Invalid API key" } });
  req.keyName = API_KEYS[token].name;
  next();
});
```

### Step 6: Hermes Config
```yaml
model:
  default: opencode/deepseek-v4-flash-free
  provider: custom
  api_key: your-api-key
  base_url: http://localhost:4000/v1
  reasoning_effort: ultra

display:
  show_reasoning: true
```

### Step 7: Deploy as Systemd Service (24/7 VM)
```bash
cat > ~/.config/systemd/user/localbridge.service << 'EOF'
[Unit]
Description=Local AI Proxy Bridge
[Service]
ExecStart=/usr/bin/node /home/user/LocalBridge/server.mjs
Restart=always
[Install]
WantedBy=default.target
EOF
systemctl --user enable localbridge && systemctl --user start localbridge
loginctl enable-linger
```

### Step 8: Hermes Telegram Gateway
```bash
hermes gateway install
echo "TELEGRAM_BOT_TOKEN=your:token" >> ~/.hermes/.env
echo "GATEWAY_ALLOW_ALL_USERS=true" >> ~/.hermes/.env
hermes gateway restart
```

## GCP VM Quick Setup
```bash
gcloud compute instances create hermes-agent --zone us-east1-b \
  --machine-type e2-small --image-family ubuntu-2404-lts-amd64 \
  --image-project ubuntu-os-cloud --boot-disk-size 20GB

# SSH with Windows space-in-username workaround
ssh -F /dev/null -o StrictHostKeyChecking=no \
  -i "C:/Users/Me/.ssh/google_compute_engine" \
  user@IP 'command'
```

## Pitfalls
- Windows username with spaces breaks gcloud SSH — use `-F /dev/null` + quoted `-i` path
- GCP zones have capacity limits — us-east1 usually available when us-central1 is full
- Node.js v18+ for native fetch; install from NodeSource if needed
- Telegram bot token in `.env` (TELEGRAM_BOT_TOKEN), not config.yaml
- Gateway needs allowlists or `GATEWAY_ALLOW_ALL_USERS=true`
- DuckDuckGo Lite classes: `result-link` for links, `result-snippet` for snippets
- Some SPAs need `format: "text"` fallback instead of markdown
