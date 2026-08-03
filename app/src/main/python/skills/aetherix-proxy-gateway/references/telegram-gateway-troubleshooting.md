# Telegram Gateway Troubleshooting (Aetherix Proxy / Hermes VM)

## Common Errors and Fixes

### 1. "No LLM provider configured for task=moa_aggregator provider=openrouter"

**Symptom:** Gateway is active but fails to respond to messages. Logs show MOA errors with openrouter/nous.

**Cause:** Hermes Gateway uses MOA (Mixture of Agents) by default, which tries to call multiple providers (openrouter, nous) as auxiliary aggregators. If these aren't configured, the call chain fails.

**Fix:**
```yaml
# ~/.hermes/config.yaml
moa:
  enabled: false
agent:
  model: opencode/mimo-v2.5-free
  provider: custom
```

### 2. Web Search Returns Empty Results

**Symptom:** `POST /v1/web/search` returns `{"results":[]}` even though the query is valid and DuckDuckGo has results.

**Root Cause:** Node.js v18's native `fetch()` to `https://lite.duckduckgo.com/lite/` returns a different HTML page than curl. The response lacks `result-link` elements entirely because DDG serves a simplified/blocked page to Node.js's HTTP client.

**Fix:** Use `child_process.execSync('curl ...')` instead of `fetch()`.

See the full code in `aetherix-proxy-gateway` skill under "Web Search Endpoint".

### 3. Telegram Adapter Stuck on "Connecting (attempt 1/8)"

**Symptom:** Gateway logs show `"Connecting to Telegram (attempt 1/8)"` repeatedly, never progressing.

**Root Cause:** The Hermes Telegram adapter uses `python-telegram-bot` with `httpx` for long-polling. On some GCP VM networks, the initial `getUpdates` long-poll request hangs indefinitely (httpx.ReadError with no details).

**Workarounds (in order of effectiveness):**
1. **Delete webhook** — force clean polling session:
   ```bash
   curl -s "https://api.telegram.org/bot<TOKEN>/deleteWebhook?drop_pending_updates=true"
   ```
2. **Reinstall gateway unit** — fixes corrupted service definition:
   ```bash
   systemctl --user stop hermes-gateway
   hermes gateway install
   systemctl --user reset-failed hermes-gateway
   systemctl --user start hermes-gateway
   ```
3. **Kill all stale PIDs** — old gateway PIDs often persist:
   ```bash
   ps aux | grep "python" | grep -v grep
   kill -9 <stale_pids>
   systemctl --user restart hermes-gateway
   ```

**Direct send always works** — even when polling is broken, you can send messages directly:
```bash
curl -s "https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<ID>&text=Hello"
```

### 3b. Webhook Conflict — "can't use getUpdates while webhook is active"

**Symptom:** After setting a webhook via `setWebhook`, the gateway's long-polling fails with:
```
telegram.error.Conflict: Conflict: can't use getUpdates method while webhook is active; use deleteWebhook to delete the webhook first
```

**Root Cause:** A webhook was set (often for testing or by another process) but never deleted. Telegram only allows one connection method at a time — either webhook OR getUpdates (long-poll), not both.

**Fix:**
```bash
# Delete webhook and drop any pending updates
curl -s "https://api.telegram.org/bot<TOKEN>/deleteWebhook?drop_pending_updates=true"

# Verify webhook is gone
curl -s "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
# Should show: {"url":""}
```

Then restart the gateway — it will use long-polling normally.

**Prevention:** Never call `setWebhook` on a bot that's expected to use long-polling. The Hermes gateway only supports long-polling (getUpdates).

### 4. Config Gets Overwritten

**Symptom:** Gateway starts using wrong model/provider suddenly.

**Root Cause:** User or other process overwrites `~/.hermes/config.yaml` with a different API's settings (e.g., tokenrouter.com).

**Fix:** Restore known-good config:
```yaml
model:
  default: opencode/mimo-v2.5-free
  provider: custom
  api_key: aetherix-master-7x9k2m4p
  base_url: http://localhost:4000/v1
  reasoning_effort: ultra
```

### 5. Gateway Won't Start (Old PID Blocking)

**Symptom:** `systemctl --user start hermes-gateway` succeeds but logs show `"Gateway already running (PID xxxxx)"`.

**Fix:**
```bash
systemctl --user stop hermes-gateway
kill -9 $(ps aux | grep "python" | grep -v grep | awk '{print $2}')
systemctl --user reset-failed hermes-gateway
systemctl --user restart hermes-gateway
```

## User Preferences for This Setup

- **Language:** Hinglish (Hindi+Urdu mix), casual tone ("bhai", "tu")
- **Style:** Fast action-first responses, minimal explanation, practical examples
- **Examples that work:** Apartment/flat analogy, pizza shop analogy
- **Avoid:** Verbose theoretical explanations, slow sequential tool calls
- **Preferred communication:** "Seedhi baat" (straight talk) with bullet-point summaries
