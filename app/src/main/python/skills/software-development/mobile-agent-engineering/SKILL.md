---
name: mobile-agent-engineering
description: Build/modify Android AI agents via embedded Linux.
---

# Mobile Agent Engineering

Guide to building or modifying Android mobile AI agents that run fully on-device — no cloud dependency, no separate gateway VM.

## Architecture Pattern

```
Android App (Kotlin/Compose)
├── Embedded Linux (libtermux)
│   ├── Python engine → agent loop + tools + skills
│   └── Node.js proxy → LLM inference endpoint
├── Android SDK APIs → phone control (SMS, call, camera, location)
└── UI layer → chat, terminal, skills/tools management
```

### MCP-style tool design (user decision — keep tools in Python, do NOT rewrite in Kotlin)
- Tools/skills/memory live in a **Python HTTP server** (`hermes_agent.py`, port 5000); the Kotlin app is only a thin client that POSTs JSON
- Start order matters: **brain (LocalBridge/LLM proxy, port 4000) starts FIRST**, then the Python tool server — the tools call the brain for the model, so the brain must be up before MCP-style tools are usable
- Benefits: zero re-testing of existing Python tools, tools stay proven, Kotlin only needs a small client + UI
- Official MCP protocol (JSON-RPC) can be layered on later — app already has an MCP screens module

## Key Components

### Linux Environment via libtermux
- `com.github.libtermux:libtermux-android` from JitPack — **NOT PUBLISHED as of 2026-07**: `https://jitpack.io/com/github/libtermux/...` returns 404/401 and Gradle fails with "Could not resolve". Do NOT add this dependency until a real JitPack release exists; the GitHub repo README advertises 1.0.0 but it's not actually published.
- If you add it anyway, expect: `Could not find com.github.libtermux:libtermux-android` + `Received status code 401 from server: Unauthorized` on jitpack.io
- Workaround while unpublished: use `Runtime.getRuntime().exec()` shell fallback for the engine, or bundle your own minimal runtime later
- Creates isolated Linux env inside app's private storage
- Multi-arch: arm64-v8a, x86_64, armeabi-v7a, x86
- **Experimental** — v1.0.0 is pre-production

### Foreground Service Pattern
- Create `HermesEngineService.kt` extending `Service`
- Start via `startForegroundService()` in `MainActivity.onCreate`
- Use notification channel for persistent "Hermes Engine" indicator
- CoroutineScope(Dispatchers.IO + SupervisorJob()) for async engine lifecycle

### Asset Bundling
- Engine files go in `app/src/main/assets/engine/`
- On first run, `AssetsManager.list()` + `copyTo()` writes them to private storage
- Python entry point: `hermes_agent.py` with HTTP server on configurable port
- Node.js entry point: `server.mjs` as lightweight LLM proxy

### Python Agent Engine
- HTTP server (http.server.HTTPServer) on localhost
- Endpoints: `/health`, `/chat`, `/tool`, `/memory`, `/tools`
- ToolRegistry pattern: register(name, handler, description)
- Memory via SQLite (conversation history + key-value store)
- Skills as .md files loaded from assets/skills/

### Permissions for Phone Control
```xml
<uses-permission android:name="android.permission.CALL_PHONE" />
<uses-permission android:name="android.permission.SEND_SMS" />
<uses-permission android:name="android.permission.CAMERA" />
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
<uses-permission android:name="android.permission.REQUEST_INSTALL_PACKAGES" />
<uses-permission android:name="android.permission.READ_CONTACTS" />
```

## CI Build
- GitHub Actions with `ubuntu-latest`, JDK 21, Android SDK
- Workflow file: `.github/workflows/build.yml` (known-good copy in `references/ci-build-debugging.md`)
- **Required**: GitHub token with `workflow` scope to push workflow files
- Alternative: add workflow file manually via GitHub web UI
- See `references/ci-build-debugging.md` for exact error strings + fixes (Gradle 9 repos, ktlint, lint uses-feature, emulator timeout, workflow scope)

## Pitfalls
1. **libtermux experimental + unpublished** — JitPack artifact 404s; remove the dependency until a real release exists (see Linux Environment section)
2. **SSH from Windows** — username spaces break gcloud SSH; use `-F /dev/null`
3. **Node.js fetch differences** — Node.js v18 fetch gets different DDG responses than curl; use `child_process.exec("curl ...")` for consistent web search
4. **GitHub workflow scope** — OAuth tokens without `workflow` scope cannot push `.github/workflows/*` files; use classic PAT with `repo` + `workflow` scopes. `gh auth refresh -h github.com -s workflow` uses a device-code browser flow that often times out in automation — pragmatic fallback: user adds the workflow file via GitHub web UI (Add file → Create new file)
5. **No on-device build** — Android apps cannot be built directly on the phone; use GitHub Actions or a development machine with Android SDK
6. **Gradle 9 `FAIL_ON_PROJECT_REPOS`** — `settings.gradle.kts` sets `repositoriesMode = FAIL_ON_PROJECT_REPOS`; adding repos via `allprojects {}` in root `build.gradle.kts` fails with "Build was configured to prefer settings repositories over project repositories". Put new repos (e.g. JitPack) inside `dependencyResolutionManagement.repositories` in settings.gradle.kts ONLY
7. **`.gitignore` silently drops engine assets** — repos with `*.py` in .gitignore will silently exclude `hermes_agent.py` from git (it stays local, never reaches GitHub, and the engine then can't find it on-device). Add with `git add -f <file>`, then verify with `git ls-files app/src/main/assets/`
8. **ktlint is strict on new Kotlin files** — CI `ktlintCheck` fails on: missing trailing commas (data classes, enums, multi-line calls), `multiline-expression-wrapping` (long expressions must break onto new lines), and `string-template-indent` for raw strings containing embedded Python. Run `./ktlint -F <file>` locally (needs JDK) before pushing, or fix by hand
9. **Android Lint `PermissionImpliesUnsupportedChromeOsHardware`** — adding phone permissions (CALL_PHONE, READ/SEND SMS, etc.) without matching `<uses-feature>` tags fails `lintDebug`. Add e.g. `<uses-feature android:name="android.hardware.telephony" android:required="false"/>` (+ camera, location as needed)
10. **CI emulator boot timeout is infra, not code** — instrumented tests fail with "could not connect to TCP port 5554: Connection refused" / "Timeout waiting for emulator to boot" on GitHub free runners; retry the run or bump the boot wait, don't chase a code bug
11. **Multi-agent force-push wipes others' work** — when another agent is concurrently editing the same repo, `git push --force` deletes their commits (and web-UI-created workflow files). Always `git fetch` + `git pull --rebase` first; resolve conflicts by keeping the remote (theirs) version and re-applying your diff
