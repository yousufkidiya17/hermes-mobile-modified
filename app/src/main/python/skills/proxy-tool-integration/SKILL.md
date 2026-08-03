---
name: proxy-tool-integration
description: "Extend Hermes tools via custom local proxy endpoints."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [proxy, tools, opencode, integration, local, api]
    related_skills: [opencode, mcporter]
---

# Proxy Tool Integration

Add custom tool capabilities to Hermes by routing through a local OpenAI-compatible proxy server (e.g., a Node.js Express proxy). When Hermes' built-in tools are slow, blocked by CAPTCHAs, or missing a capability, a local proxy can expose fast API-driven replacements.

## When to Use

- Hermes browser tools are slow or blocked by CAPTCHAs
- User has a local Node.js/Express proxy (like Aetherix Proxy Gateway)
- You need fast web search/fetch without browser overhead
- You want to add custom tools that Hermes doesn't natively provide
- User asks to integrate OpenCode's fast web tools into Hermes

## Architecture

```
Hermes → terminal/curl → LocalBridge (Express.js :4000) → Upstream API
                                                        → DuckDuckGo Lite
                                                        → OpenCode Zen API
```

The key insight: OpenCode's web_search and webfetch tools are fast because they use direct HTTP fetch (not a browser). These same endpoints can be added to any local OpenAI-compatible proxy.

## Adding Web Search & Fetch Endpoints

### Prerequisites
- Node.js Express server running locally
- Dependencies: `npm install turndown htmlparser2`

### Endpoint: Web Fetch

```javascript
// POST /v1/web/fetch
// Input: { url, format: "markdown"|"text"|"html" }
// Output: { url, contentType, format, output }
```

Direct HTTP fetch with:
- User-Agent: Mozilla/5.0 (Windows...)
- Accept-Language: en-US,en;q=0.9
- 30s timeout, 5MB max response
- HTML → Markdown conversion via TurndownService
- HTML → Text extraction via htmlparser2

### Endpoint: Web Search

```javascript
// POST /v1/web/search
// Input: { query, action: "search"|"open_page"|"find", url?, pattern? }
// Output: { results: [{ title, url, snippet }] }
```

Uses DuckDuckGo Lite API:
- POST to https://lite.duckduckgo.com/lite/ with form data `q=<query>`
- Parse HTML response for `class="result-link"` (a tags) and snippets
- 15s timeout

### Usage from Hermes

```bash
# Search
curl -X POST http://localhost:4000/v1/web/search \
  -H "Content-Type: application/json" \
  -d '{"query":"search term"}'

# Fetch URL
curl -X POST http://localhost:4000/v1/web/fetch \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com","format":"markdown"}'
```

## Comparison: Built-in Browser vs Proxy Tools

| Aspect | Hermes Browser Tool | Proxy Fetch/Search |
|--------|-------------------|-------------------|
| Speed | 🐢 30-60s | ⚡ 1-3s |
| CAPTCHA | ❌ Gets blocked | ✅ Bypasses (lite sites) |
| Format | HTML only | text/markdown/html |
| Reliability | 🟡 Depends on JS rendering | 🟢 Direct HTTP |

## Creating the Skill

Create a Hermes skill that teaches the agent to use these proxy endpoints:

```
When user asks to search: use terminal curl to POST /v1/web/search
When user asks to fetch a URL: use terminal curl to POST /v1/web/fetch
Parse JSON response, display results cleanly.
```

## Pitfalls

- DuckDuckGo Lite HTML structure can change — `result-link` class may need updating
- Some sites return HTML instead of clean text even in "text" format
- TurndownService required for HTML→Markdown conversion
- Rate limiting: DuckDuckGo Lite may throttle frequent requests
- The proxy server must be running before Hermes tries to use these endpoints
- Indian Railways/IRCTC sites use JS-rendered content — these endpoints cannot extract seat availability numbers from them
- **Windows SSH path spaces**: Username with spaces (e.g. "Mohd yousuf") breaks gcloud SSH — see references/gcp-vm-deploy.md for the `-F /dev/null` workaround
- **Gateway allowlist**: Without `GATEWAY_ALLOW_ALL_USERS=true`, Telegram gateway blocks unknown senders
- **🚨 Node.js fetch vs curl on GCP**: Node.js v18's native `fetch()` gets a DIFFERENT/shorter response from DuckDuckGo Lite than `curl` — `result-link` class is missing from Node.js response entirely. This is a DuckDuckGo server-side detection issue. **Fix:** Use `child_process.execSync('curl ...')` instead of `fetch()` inside the search handler, or use `https://html.duckduckgo.com/html/` as the search endpoint.
- **Killing services via SSH**: `pkill -f` with patterns like `hermes` or `server` matches the SSH command itself — kills the SSH session. Use targeted `kill <PID>` instead, or use `ps aux | grep -v grep | grep [p]attern` to get PIDs first.
- **MOA errors**: If gateway logs show "No LLM provider configured for task=moa_aggregator provider=openrouter", add `moa: enabled: false` to config.yaml — disables the Mixture-of-Agents feature that tries external providers.
- **Webhook vs polling conflict**: `setWebhook` and `getUpdates` polling cannot co-exist. If gateway errors with "can't use getUpdates method while webhook is active", delete webhook: `curl https://api.telegram.org/bot<TOKEN>/deleteWebhook`

## Remote Deployment (GCP VM)

See `references/gcp-vm-deploy.md` for the complete deployment workflow:
1. VM creation and zone selection
2. Windows SSH workaround for spaced usernames
3. Hermes + LocalBridge install on VM
4. **Systemd services for persistence** (NOT nohup — dies on SSH disconnect):
   - LocalBridge service → see `references/systemd-localbridge.md`
   - Hermes gateway → `hermes gateway install` creates it automatically
5. Config template: 7 model aliases, ultra reasoning, vision flag, **MOA disabled**
6. Telegram gateway with systemd service for 24/7 operation
