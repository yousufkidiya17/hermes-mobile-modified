---
name: custom-api-bridge
description: "Bridge Hermes to any OpenAI-compatible API via local proxy."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [proxy, bridge, custom-provider, openai-compatible, free-models, local]
---

# Custom API Bridge — Local Proxy for Hermes

Connect Hermes to any OpenAI-compatible API (free models, local LLMs, third-party providers) via a local Node.js Express proxy. Bypasses provider limitations, adds custom endpoints, and keeps your Hermes config clean.

## When to Use
- User has free/cheap model access through a third-party API (OpenCode, Together AI, DeepInfra, etc.)
- Need to add tools like web search or web fetch that Hermes doesn't natively support
- Want to route Hermes through a local proxy for rate limiting, logging, or model transformation
- Need OpenAI-compatible endpoint for a non-standard API

## Architecture

```
Hermes (AI Agent)
    ↓ provider: custom
    ↓ base_url: http://localhost:PORT/v1
LocalBridge (Node.js Express server)
    ↓ API key + model mapping
External API (OpenCode Zen / Together / DeepInfra / etc.)
```

## Step 1: Create the Proxy Server

Create a Node.js Express server (e.g. `server.mjs`):

```javascript
import express from "express";
const app = express();
app.use(express.json({ limit: "10mb" }));

const PROXY_PORT = 4000;
const API_BASE = "https://api.example.com/v1";  // Your API endpoint

// Model mapping — local ID → external API ID
const MODELS = [
  { id: "provider/model-name", apiId: "model-name" },
];

// POST /v1/chat/completions — passthrough with model mapping
app.post("/v1/chat/completions", async (req, res) => {
  const { model, messages, stream, tools } = req.body;
  const entry = MODELS.find(m => m.id === model);
  const apiModel = entry ? entry.apiId : model;

  const body = { model: apiModel, messages, stream };
  if (tools?.length) body.tools = tools;

  try {
    const apiRes = await fetch(`${API_BASE}/chat/completions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    // Handle streaming vs non-streaming
    if (stream) {
      res.setHeader("Content-Type", "text/event-stream");
      for await (const chunk of apiRes.body) res.write(chunk);
      res.end();
    } else {
      const data = await apiRes.json();
      res.json(data);
    }
  } catch (err) {
    res.status(500).json({ error: { message: err.message } });
  }
});

// GET /v1/models — list available models
app.get("/v1/models", (req, res) => {
  res.json({
    object: "list",
    data: MODELS.map(m => ({ id: m.id, object: "model" })),
  });
});

app.listen(PROXY_PORT, () => console.log(`Bridge on :${PROXY_PORT}`));
```

## Step 2: Add Web Search & Web Fetch Endpoints

These give Hermes fast search/fetch without browser CAPTCHA issues.

### Web Fetch Endpoint
```javascript
app.get("/v1/web/fetch", async (req, res) => {
  const url = req.query.url;
  const format = req.query.format || "markdown";
  try {
    const response = await fetch(url, {
      headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" },
    });
    const html = await response.text();
    // Return as text (strip HTML) or markdown
    const text = html.replace(/<[^>]*>/g, "").replace(/\s+/g, " ").trim();
    res.json({ url, contentType: response.headers.get("content-type"), format, output: text });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});
```

### Web Search Endpoint
```javascript
app.get("/v1/web/search", async (req, res) => {
  const q = encodeURIComponent(req.query.q || "");
  try {
    const response = await fetch(`https://lite.duckduckgo.com/lite/?q=${q}`);
    const html = await response.text();
    // Parse result links from HTML
    const links = [...html.matchAll(/<a[^>]*href="([^"]*)"[^>]*>(.*?)<\/a>/g)]
      .map(m => ({ url: m[1], title: m[2].replace(/<[^>]*>/g, "") }))
      .filter(l => l.url.startsWith("http"));
    res.json({ query: req.query.q, results: links.slice(0, 10) });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});
```

## Step 3: Configure Hermes

In Hermes config.yaml (use `hermes config set`):
```yaml
model:
  default: provider/model-name
  provider: custom
  base_url: http://localhost:4000/v1
```

Or set via CLI:
```bash
hermes config set model.provider custom
hermes config set model.base_url http://localhost:4000/v1
hermes config set model.default provider/model-name
```

## Step 4: Custom Provider Profile (optional)

For advanced features (vision, reasoning control, token limits), create a provider profile:

```python
from providers import register_provider
from providers.base import ProviderProfile

class CustomProfile(ProviderProfile):
    def build_api_kwargs_extras(self, **ctx):
        return {}, {}

custom = CustomProfile(
    name="custom",
    base_url="",
    default_max_tokens=65536,
    supports_vision=True,
)
register_provider(custom)
```

Save as `custom_provider_init.py` in Hermes skills or plugins directory.

## Quick Test
```bash
# Test the bridge
curl http://localhost:4000/v1/models

# Test web search
curl "http://localhost:4000/v1/web/search?q=test+query"

# Test chat
curl -X POST http://localhost:4000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"provider/model-name","messages":[{"role":"user","content":"hello"}]}'
```

## Pitfalls
- **Windows username with spaces** (e.g. "Mohd yousuf") causes gcloud SSH/commands to break. The shell splits on the space. Fix: use `gcloud.cmd` via cmd.exe or quote the full path `/c/Users/Mohd\ yousuf/...`. For gcloud SSH, the error `'C:\\Users\\Mohd' is not recognized` means the path split. Workaround: use `--command "simple"` only, or create a helper batch file.
- **Free APIs may have rate limits or intermittent availability** — the vision auxiliary model may go down ("Upstream request failed"). Vision works through `supports_vision=True` in the custom provider profile (custom_provider_init.py), NOT through native model capability. When vision fails, try a different model/provider or use Tesseract OCR.
- **Model switches are provider-side** — the remote API (OpenCode Zen) can change your model mid-session. Watch the system message "[System: The active model...]" to know what model you're actually using.
- Streaming requires proper SSE handling in both proxy and Hermes
- Always test model mapping works before relying on tool calling
- Web search via DuckDuckGo Lite may get rate-limited with heavy use; add caching for production
