# Bundling the REAL Hermes Agent (188 skills / 29+ tools) into the Phone App

User requirement (2026-08, explicit): "jo pc me chal raha hai usko phone me kerna hai" —
the phone app must run the SAME Hermes Agent that runs on the PC (full skills + tools),
NOT the mini engine (8 tools / 3 skills) used for the first integration milestone.

## Why the mini engine exists (honest framing for the user)

The first working milestone embedded a custom `hermes_agent.py` (8 tools, 3 skills).
That is NOT "Hermes" — it's a lightweight clone. The user's catch:
"hermes ki 145+ default skills hain, 29+ tools hain — tune asli hermes launch nahi kiya."
This is 100% correct. The Skills/Tools screens in the app are CLIENT-SIDE:
`SkillsViewModel` → `ApiClient.hermesApi.getSkills()` → `GET api/skills`,
`ToolsetsScreen` → `loadToolsets()` → `GET api/toolsets`. They display whatever the
gateway serves. With the mini engine the gateway serves nothing for those endpoints,
so the screens show empty lists — same as when there was no gateway at all.

## Real Hermes Agent anatomy (PC install, source of truth)

Location: `C:\Users\Mohd yousuf\AppData\Local\hermes\hermes-agent\` (git-installed source).
- **188 `SKILL.md` files** in the source tree (`find . -name SKILL.md | wc -l` ≈ 188)
- Python packages: `agent/` (core), `hermes/`, `gateway/`, `hermes_cli/`, `acp_adapter/`, `cron/`, `apps/`
- `hermes_agent.egg-info/` + `pyproject.toml` (exact-pinned deps)
- Launcher: `venv/Scripts/hermes.exe` on Windows

## Dependency reality check (the blocker)

`pyproject.toml` has **69 exact-pinned deps** (`==X.Y.Z` — policy since 2026-05-12 to
dodge supply-chain worms). Core ones: `openai==2.24.0`, `httpx[socks]==0.28.1`,
`rich`, `pydantic==2.13.4`, `pyyaml`, `ruamel.yaml`, `cryptography`, `prompt_toolkit`,
`croniter`, `tenacity`, `jinja2`, plus a long tail of optional extras
(anthropic, exa-py, edge-tts, faster-whisper, asyncpg, slack-bolt, ...).

**Chaquopy compatibility check (verified this session):**
- Pure-Python wheels (httpx, rich, openai, jinja2, prompt_toolkit, croniter) → fine
- **Native extensions are the wall:**
  - `pydantic-core` = **Rust** native (pulled by pydantic 2.x) — no Android wheel
  - `cryptography` = C native — no Android wheel
  - `ruamel.yaml` / `pyyaml` = C extensions — no Android wheel
  - Chaquopy wheel-doc lookups for these return 404
- Consequence: a naive `pip { install("hermes-agent") }` in the Chaquopy block will
  fail on native deps. Realistic target is **~90% of Hermes** (pure-Python core +
  all 188 skills + pure-python tools); native-dependent pieces need a later,
  separate strategy (skip, stub, or pure-Python reimplementation).

## Realistic plan (in order)

1. Copy the pure-Python package dirs (`agent/`, `hermes/`, `gateway/`, `hermes_cli/` core
   files, `hermes_*.py` top-level modules) into `app/src/main/python/hermes-agent/`
   (or a flattened layout Chaquopy can import). Add the pure-Python deps to the
   Chaquopy `pip {}` block; do NOT add pydantic/cryptography/ruamel/yaml initially.
2. Copy all 188 `SKILL.md` files into `app/src/main/python/skills/` (skills loader
   globs `*.md`). Verify count on device via `get_status()["skills"]`.
3. Make the on-device gateway serve the REAL endpoints the app screens call:
   `GET api/skills`, `GET api/toolsets` (and `GET api/model/options` for the model
   picker — see SKILL.md model-picker gap). Mini-engine handlers can be kept for
   chat, but the list screens need real data sources.
4. Test on PC first (same pure-Python code), then emulator, then phone — same
   tiered-testing flow as the mini engine milestone.

## Estimated APK impact

- Skills are small `.md` files (188 × few KB) → negligible
- Hermes package + pure deps → APK grows roughly +40–60 MB (user phone has ~1.7 GB
  free; fits, but watch it)

## User communication preferences observed this session (Hinglish, direct)

- **"jitna puch raha hu bas utna bata"** — answer EXACTLY the question asked, in the
  shortest form that is still true. Do not front-load a full architecture recap when
  the user asked one narrow thing (e.g. "phone me terminal hai kya?" → yes/no +
  one-line how, not the whole pipeline).
- **"sab test kerke final ker"** — the user wants ONE complete test pass (chat +
  vision + skills + status on the emulator) and then a final verdict, not
  piece-by-piece updates with a push after each micro-step.
- Analogies land: kitchen/menu-card, all-in-one machine, TV/remote. Use them for
  "what changed vs what stayed" explanations.
