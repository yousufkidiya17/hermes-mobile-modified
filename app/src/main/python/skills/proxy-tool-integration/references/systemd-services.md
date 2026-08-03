# Systemd Services for VM Persistence

Services started with `nohup` in an SSH session die when the SSH connection closes. Use systemd user services for 24/7 operation.

## LocalBridge (Node.js Proxy) Service

Create `~/.config/systemd/user/localbridge.service`:

```ini
[Unit]
Description=Aetherix LocalBridge Proxy
After=network.target

[Service]
ExecStart=/usr/bin/node /home/<user>/LocalBridge/server.mjs
Restart=always
RestartSec=5
WorkingDirectory=/home/<user>/LocalBridge

[Install]
WantedBy=default.target
```

Enable and start:

```bash
systemctl --user daemon-reload
systemctl --user enable --now localbridge
systemctl --user status localbridge
```

## Hermes Gateway Service

Created automatically by `hermes gateway install`. Management:

```bash
systemctl --user start hermes-gateway
systemctl --user stop hermes-gateway
systemctl --user restart hermes-gateway
systemctl --user status hermes-gateway
journalctl --user -u hermes-gateway -n 50 --no-pager
```

## Gateway Log Monitoring

```bash
# All Telegram-related logs
journalctl --user -u hermes-gateway --since "5 min ago" --no-pager | grep -i telegram

# Errors only
journalctl --user -u hermes-gateway -p err

# Follow live
journalctl --user -u hermes-gateway -f
```

## Clean Restart (When Stuck)

If the gateway enters a crash loop or PID conflict:

```bash
# 1. Kill ALL hermes gateway processes (careful: don't match SSH command)
ps aux | grep -v grep | grep "hermes.*gateway" | awk '{print $2}' | xargs kill -9

# 2. Reset systemd failure counter
systemctl --user reset-failed hermes-gateway

# 3. Fresh start
systemctl --user start hermes-gateway
```

**Don't use `pkill -f hermes`** — it matches the SSH command itself and kills the SSH session.

## Multi-Flat Architecture

Run multiple independent services on one VM using separate systemd services:

| Flat | Service | Config | Token/Key |
|------|---------|--------|-----------|
| Telegram Bot | localbridge + hermes-gateway | ~/.hermes/config.yaml | TELEGRAM_BOT_TOKEN |
| Vibe Coder | (cron-based) | GitHub token | gh CLI |
| Mobile App | (stateless, hits proxy directly) | VM_IP:4000/v1 | API key |

## Linger for User Services

Enable lingering so services persist after SSH logout:

```bash
loginctl enable-linger $(whoami)
```

This is done automatically by `hermes gateway install`.
