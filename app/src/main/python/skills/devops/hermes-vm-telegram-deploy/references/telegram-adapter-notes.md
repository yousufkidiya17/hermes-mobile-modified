# Telegram Adapter — Known Error Patterns

Captured from live session 2026-07-29/30 on hermes-vibe-coder (e2-small, us-east1-b).

## Error: httpx.ReadError

```
WARNING hermes_plugins.telegram_platform.adapter: [Telegram] Telegram network _redact_telegram_error_text(error), scheduling reconnect: httpx.ReadError:
WARNING hermes_plugins.telegram_platform.adapter: [Telegram] Telegram network error (attempt 1/10), reconnecting in 5s. Error: httpx.ReadError:
```

**Pattern:** Periodic disconnects every few minutes. Gateway auto-reconnects. Not fatal — normal for long-polling on GCP. The error text is redacted by Hermes.

## Error: send_path_degraded

```
WARNING gateway.platforms.base: [Telegram] Send failed (attempt 1/2, retrying in 2.9s): send_path_degraded
ERROR gateway.platforms.base: [Telegram] Failed to deliver response after 2 retries: send_path_degraded
```

**Pattern:** Outgoing messages fail. Usually transient. Gateway retries twice then gives up. Underlying cause likely httpx.ReadError on the receive side cascading.

## Error: Webhook Conflict

```
telegram.error.Conflict: Conflict: can't use getUpdates method while webhook is active; use deleteWebhook to delete the webhook first
```

**Fix:**
```bash
curl -s "https://api.telegram.org/bot<TOKEN>/deleteWebhook?drop_pending_updates=true"
```
Then restart gateway. The `setWebhook` call earlier in the session caused this.

## Error: MOA No LLM Provider

```
ERROR agent.conversation_loop: API call failed after 3 retries. No LLM provider configured for task=moa_aggregator provider=openrouter.
```

**Root cause:** Default config enables MOA (Mixture of Agents) which tries openrouter/nous as auxiliary providers. Neither is configured.

**Fix:** Add to config.yaml:
```yaml
moa:
  enabled: false
```

## Error: Config Overwrite

config.yaml was overwritten from:
```
model: opencode/mimo-v2.5-free, base_url: localhost:4000/v1
```
to:
```
model: moonshotai/kimi-k3-free, base_url: https://api.tokenrouter.com/v1
```

**Root cause:** User tested tokenrouter.com API key in a script. Gateway or hermes setup may have synced the change.

**Fix:** Rewrite config.yaml from backup. Don't run `hermes setup` on a VM with custom provider config.

## Error: Gateway Already Running

```
❌ Gateway already running (PID 16349).
```

**Root cause:** Killed gateway process without systemd noticing, or multiple restarts creating PID leaks.

**Fix:** Clean restart:
```bash
kill -9 $(pgrep -f "python.*gateway")
systemctl --user reset-failed hermes-gateway
systemctl --user start hermes-gateway
```

## Error: ZONE_RESOURCE_POOL_EXHAUSTED

```
A e2-small VM instance is currently unavailable in the us-central1-a zone
```

**Fix:** Try different zones: us-east1-b (worked), us-west1-a, us-central1-c. us-central1-a/b often have no e2-small capacity.

## Shell Tips for Windows-with-Space Username

gcloud.cmd from git-bash: the space in "Mohd yousuf" breaks quoting.

**Working approach:**
```bash
ssh -F /dev/null -o StrictHostKeyChecking=no \
  -i "C:/Users/Your Name/.ssh/google_compute_engine" \
  user@<IP> 'command'
```

**All-in-one for scp:**
```bash
scp -F /dev/null -o StrictHostKeyChecking=no \
  -i "C:/Users/Your Name/.ssh/google_compute_engine" \
  "C:/path/to/file" user@<IP>:~/dest/
```

**Check gcloud active project:**
```bash
gcloud config get-value project
```

**List projects:**
```bash
gcloud projects list --format="table(project_id, name)"
```

**Delete empty project:**
```bash
gcloud projects delete <project-id> --quiet
```
