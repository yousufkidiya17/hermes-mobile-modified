# Deploying Proxy + Hermes to GCP VM

End-to-end setup for running the Aetherix Proxy Gateway + Hermes on a Google Cloud VM, with Telegram bot integration.

## VM Creation

```bash
# Create e2-small (1 vCPU, 2GB) — ~$7/mo, enough for proxy + hermes
gcloud compute instances create hermes-vibe-coder \
  --zone us-east1-b \                    # Avoid us-central1 (pool exhausted)
  --machine-type e2-small \
  --image-family ubuntu-2404-lts-amd64 \
  --image-project ubuntu-os-cloud \
  --boot-disk-size 20GB \
  --tags hermes-vm

# Open port 4000 for proxy
gcloud compute firewall-rules create allow-proxy-4000 \
  --allow tcp:4000 --target-tags hermes-vm
```

## Windows SSH Workaround

**Critical:** On Windows, if the username contains a space (e.g. `Mohd yousuf`), the auto-generated `.ssh/config` breaks. The IdentityFile lines like `C:\Users\Mohd yousuf\.ssh\google_compute_engine` are parsed as two tokens. This causes ALL ssh commands to fail with `keyword identityfile extra arguments`.

**Fix:** Use `-F /dev/null` to skip the broken config file entirely:

```bash
ssh -F /dev/null \
  -o StrictHostKeyChecking=no \
  -i "C:/Users/Mohd yousuf/.ssh/google_compute_engine" \
  kidiyayousuf17@<VM_IP> \
  "command here"
```

Also works for SCP:
```bash
scp -F /dev/null \
  -o StrictHostKeyChecking=no \
  -i "C:/Users/Mohd yousuf/.ssh/google_compute_engine" \
  source_file \
  kidiyayousuf17@<VM_IP>:~/destination/
```

Do NOT try to fix the SSH config file — Hermes' write protection blocks writes to `~/.ssh/config`.

## Hermes Installation on VM

```bash
# 1. Prerequisites (VM)
sudo apt update && sudo apt install -y curl nodejs npm python3 python3-pip git

# 2. Install Hermes
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
# → Expect 70 skills synced, venv created, hermes command at ~/.local/bin/hermes

# 3. Start LocalBridge (copy server.mjs from desktop)
cd ~ && mkdir LocalBridge
# SCP from desktop:
scp -F /dev/null -i "C:/Users/..." server.mjs kidiyayousuf17@IP:~/LocalBridge/
cd ~/LocalBridge && npm init -y && npm install express turndown htmlparser2

# 4. Start proxy in background
cd ~/LocalBridge && nohup node server.mjs > server.log 2>&1 &

# 5. Test proxy
curl -s http://localhost:4000/health
curl -s -X POST http://localhost:4000/v1/web/search \
  -H "Content-Type: application/json" \
  -d '{"query":"test"}'
curl -s -X POST http://localhost:4000/v1/web/fetch \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com","format":"markdown"}'
```

## Hermes Config Template

```yaml
model:
  default: opencode/mimo-v2.5-free
  provider: custom
  api_key: aetherix-master-7x9k2m4p
  base_url: http://localhost:4000/v1
  reasoning_effort: ultra

display:
  show_reasoning: false          # off for Telegram
  streaming: true

# Model aliases for /model command switching
model_aliases:
  deepseek: { model: opencode/deepseek-v4-flash-free, provider: custom, base_url: http://localhost:4000/v1, api_key: aetherix-master-7x9k2m4p }
  mimo:     { model: opencode/mimo-v2.5-free,         provider: custom, base_url: http://localhost:4000/v1, api_key: aetherix-master-7x9k2m4p }
  nemotron: { model: opencode/nemotron-3-ultra-free,  provider: custom, base_url: http://localhost:4000/v1, api_key: aetherix-master-7x9k2m4p }
  ling:     { model: opencode/ling-3.0-flash-free,    provider: custom, base_url: http://localhost:4000/v1, api_key: aetherix-master-7x9k2m4p }
  bigpickle:{ model: opencode/big-pickle,             provider: custom, base_url: http://localhost:4000/v1, api_key: aetherix-master-7x9k2m4p }

custom_provider:
  supports_vision: true
  supports_reasoning: true
  thinking_mode: true
  default_max_tokens: 65536
  default_reasoning_effort: ultra
```

## Telegram Gateway Setup

```bash
# Add bot token to .env
echo "TELEGRAM_BOT_TOKEN=123456:ABC-DEF..." >> ~/.hermes/.env
echo "GATEWAY_ALLOW_ALL_USERS=true" >> ~/.hermes/.env

# Install & start gateway
hermes gateway install    # Creates systemd user service
systemctl --user start hermes-gateway
systemctl --user status hermes-gateway

# The gateway auto-restarts on VM boot via systemd linger
```

## GCP Zone Availability Issues

- `us-central1-a`, `us-central1-b` — **e2-small exhausted** (common)
- `us-east1-b` — usually works for e2-small
- If e2-small unavailable, try `e2-micro` or a different zone
- Disk <200GB warning is harmless for 20GB boot disks

## Pitfalls

- **Windows SSH path spaces**: Always use `-F /dev/null` and quote the IdentityFile path
- **DuckDuckGo Lite HTML changes**: The CSS class search relies on `class="result-link"` on `<a>` tags — verify if search returns empty results
- **IRC TC/Indian Railways sites**: JS-rendered, cannot extract seat availability numbers via web fetch
- **Gateway allowlist**: Without `GATEWAY_ALLOW_ALL_USERS=true`, Telegram gateway blocks all unknown senders
- **apt lock**: Fresh VMs may have background apt process — check with `sudo lsof /var/lib/dpkg/lock-frontend` before installing
- **Vision**: OpenCode free models (DeepSeek, Mimo) don't natively support vision — `supports_vision: true` is a Hermes flag but actual image analysis may fail
