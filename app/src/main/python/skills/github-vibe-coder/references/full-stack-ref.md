# Full Stack Reference — Hermes GitHub Vibe Coder

## Complete Architecture

```
Layer 1: Host — VPS ($5-10/mo, 24/7)
Layer 2: Platform — Hermes Agent (orchestrator)
Layer 3: Model — Free/paid LLM via proxy or API
Layer 4: Tools — gh CLI, OpenHands, OpenCode
Layer 5: Delivery — Telegram (built-in Hermes gateway)
Layer 6: Memory — Hermes persistent memory
```

## Recommended VPS Specs

| Provider | Plan | Cost | Specs |
|----------|------|------|-------|
| DigitalOcean | Basic Droplet | $6/mo | 1 vCPU, 1GB RAM |
| Hetzner | CX22 | ~€4/mo | 2 vCPU, 4GB RAM |
| Google Cloud | e2-micro (free tier) | Free | 0.25 vCPU, 1GB RAM |
| Google Cloud | e2-medium | ~$25/mo | 2 vCPU, 4GB RAM |

## GitHub Token Scopes Required

- `repo` — full control of private repos
- `workflow` — update GitHub Actions workflows
- `public_repo` — contribute to public repos

## Sample Cron: Daily PR

```yaml
name: daily-vibe-code
schedule: "0 9 * * 1-5"  # Weekdays at 9am
prompt: |
  Look at GitHub trending today.
  Find 1 good-first-issue in a language I know.
  Fork, fix, commit, PR.
  Log progress to memory.
  Telegram me the result.
deliver: telegram
```

## Troubleshooting

- `gh auth status` fails → regenerate token
- PR merge conflicts → fork sync cron needed
- CI fails on PR → assign OpenHands to fix and update
- Rate limited → add sleep between API calls
