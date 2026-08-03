---
name: mobile-ai-agent-development
description: "Embed Termux, local models, and AI skills in Android apps."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [android, windows, linux]
metadata:
  hermes:
    tags: [android, kotlin, termux, mobile-ai, agent, apk]
    related_skills: [aetherix-proxy-gateway, local-ai-proxy]
---

# Mobile AI Agent Development

Modify Android apps (like **Hermes Mobile** / `Hy4ri/hermes-mobile`) to create a standalone AI agent on the phone — no VM needed.

## 4-Layer Architecture

```
📱 APK ├── Local Model Proxy (Kotlin calls model API directly — NO Node.js needed)
      ├── Embedded Python (Chaquopy — bundles interpreter in APK)
      ├── Skills Engine (320+ skills)
      └── Tools Engine (search, fetch, file, terminal)
```

## Key Discoveries

### ✅ Chaquopy = the runtime (NOT libtermux)
**Use Chaquopy (`com.chaquo.python`) — libtermux is a dead end.** `libtermux/libtermux-android` is NOT published to JitPack (HTTP 404 on the POM), has no releases/tags, and is marked experimental. Chaquopy is mature (v17.0.0, Dec 2025), MIT-licensed, and explicitly supports AGP 9.0–9.2 (verified via changelog). Setup:
- Root `build.gradle.kts`: `id("com.chaquo.python") version "17.0.0" apply false`
- App `build.gradle.kts`: apply plugin + `chaquopy { defaultConfig { version = "3.11" } sourceSets { getByName("main") { srcDir("src/main/python") } } }`
- **`ndk.abiFilters` is REQUIRED** in `android.defaultConfig` or build fails: `abiFilters += listOf("arm64-v8a", "armeabi-v7a", "x86_64")`
- Python code lives in `app/src/main/python/` — Kotlin calls it directly via `com.chaquo.python.Python` API (`Python.start(AndroidPlatform(context))`, `py.getModule("hermes_agent").callAttr("process_chat", msg)`). No HTTP server needed between Kotlin and Python.
- Keep Python stdlib-only (urllib, sqlite3, http.server) → zero pip deps, smaller APK.
- **CI runners need build-time Python**: add `actions/setup-python@v5` with `python-version: '3.11'` to EVERY Gradle job, or you get `Couldn't find Python 3.11` + configuration-cache external-process errors.

### Hermes Mobile (Hy4ri/hermes-mobile)
224 Kotlin files, Gateway API client. Already has skills/tools UI but needs Gateway backend. Default `ConnectionProfile` points at `127.0.0.1:9119` — "Dashboard unreachable" error means no gateway is running anywhere (phone, VM, or PC), NOT an app bug. The embedded engine must serve the gateway role on-device for standalone mode.

### LocalBridge → drop Node.js entirely
On Android there is no `node` binary; stock Android has no Node/Python. Instead of porting server.mjs to Kotlin, let Kotlin call the model API directly with OkHttp (app already has it) and keep Python only for tools/skills. One runtime instead of two.

### DuckDuckGo Gotcha
Node.js fetch vs curl get different HTML from DDG Lite. OkHttp works on Android.

## Pitfalls
1. **`gh` OAuth token lacks `workflow` scope** — pushing `.github/workflows/*.yml` fails with "refusing to allow an OAuth App ... without `workflow` scope". Even `gh api PUT` to a `.github/workflows/` path returns **404 (not 403!)** — GitHub hides the path, so it looks like a repo/path bug. Root-level files PUT fine. Fix: `gh auth refresh -h github.com -s workflow` (device-code flow) — see references/gh-workflow-scope.md. Cheapest workaround: create workflow files via the GitHub web UI (Add file → Create new file) and keep them out of `git push`.
2. **`.gitignore` with `*.py` silently excludes engine files** — Python assets never get committed; `git add -f app/src/main/python/hermes_agent.py` needed. Always `git ls-files app/src/main/assets` + check GitHub contents API after pushing new Python files.
3. **ktlint CI loop** — Hermes Mobile enforces ktlint 1.2.1 in CI (trailing commas everywhere, 120-char max line, multiline expressions start on new line, no blank line after class opening brace, ASCII import order). A single style slip = full CI failure (~7 jobs). Run ktlint locally before push when JDK available, or expect 1-2 fix cycles.
4. **CI emulator flakiness is infra, not code** — "Timeout waiting for emulator to boot" / `could not connect to TCP port 5554` = GitHub runner issue. Fix in workflow: fresh AVD creation + `no-snapshot` + retry script; don't chase it as an app bug.
5. Gateway dependency is the main blocker (app needs a gateway at :9119 to show anything)
6. APK grows ~100MB+ with embedded runtime
7. Windows SSH: always `-F /dev/null`
8. Never `pgrep -f hermes` in SSH
9. Disable MOA if openrouter/nous errors in Telegram gateway

## Verify APK Before Installing (user requires this)
User will not blind-install: always inspect the APK before handing it over:
- `unzip -t app.apk` (valid ZIP)
- `unzip -l` → confirm engine assets present (`assets/engine/...` or bundled python)
- Confirm Kotlin service classes compiled: `unzip -p app.apk classes*.dex | grep -ao "Lcom/m57/hermescontrol/service/HermesEngineService;"` (string search across dex files)
- Binary manifest: extract `AndroidManifest.xml` and search UTF-8 AND UTF-16-LE for permission names / uses-feature / service class.

## Key Files to Modify
`ConnectionProfile.kt`, `HermesApiService.kt`, `ApiClient.kt`, `ChatViewModel.kt`, `ConnectScreen.kt`, `SkillsViewModel.kt`, `build.gradle.kts`, `settings.gradle.kts` (add jitpack/maven repos there, NOT root build.gradle — Gradle 9 `FAIL_ON_PROJECT_REPOS` rejects project repos), `.github/workflows/android.yml` (setup-python).

## User Rules
**Ask before acting.** Explain plan, get approval. User is new to dev, prefers analogies, step-by-step, Hinglish, hands-on. Explain each fix's root cause in plain language before applying it.
