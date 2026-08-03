---
name: hermes-mobile-embedding
description: "Embed Hermes Agent into Android (Chaquopy Python + on-device gateway)."
---

# Hermes Mobile Embedding Guide

Embed a full Hermes agent (LocalBridge proxy + Python skills/tools engine + Linux terminal) into the Hy4ri/hermes-mobile Android app so it works standalone without a remote VM.

## Architecture

```
Modified APK (single install)
├── ✅ Chaquopy (embedded Python via JNI) → hermes_agent.py engine (tools, skills, memory)
├── ✅ Kotlin direct model calls (OkHttp) → DeepSeek/Mimo via OpenCode Zen API (NO Node.js needed)
├── Android SDK built-in → SMS, Call, Camera, Location, Contacts, Install/Uninstall
├── Foreground Service → Auto-start on app open
└── Existing Compose UI → Chat, Skills, Tools screens already built
```

**⚠️ RUNTIME DECISION (2026-08):** The permanent runtime is **Chaquopy** (`com.chaquo.python`), NOT libtermux. Chaquopy is a published, stable Gradle plugin that bundles the Python interpreter inside the APK (JNI, no Termux app, no libtermux wait). See `references/chaquopy-integration.md` for the full setup, requirements, and CI integration. The old libtermux approach below is historical — re-check only if Chaquopy ever becomes unavailable.

**🎯 REAL vs MINI engine (2026-08, user-required):** The first milestone embeds a custom mini `hermes_agent.py` (8 tools / 3 skills). The user explicitly requires the FULL Hermes Agent instead — "jo pc me chal raha hai usko phone me kerna hai" (188 skills, 29+ tools). The Skills/Tools app screens are CLIENT-side (`GET api/skills`, `GET api/toolsets`) and show empty unless the gateway serves real data. Full anatomy, Chaquopy dep-compatibility analysis (native wheels pydantic-core/cryptography/yaml are the wall → ~90% achievable), plan, and user comms prefs: **`references/real-hermes-bundling.md`**.

## Key Technical Steps

### 1. Build System (Gradle 9)

- **Kotlin 2.4.10**, AGP 9.0.1, minSdk 26, targetSdk 36
- Add JitPack to `settings.gradle.kts` NOT `build.gradle.kts`:
  ```kotlin
  // settings.gradle.kts — dependencyResolutionManagement block
  maven { url = uri("https://jitpack.io") }
  ```
- `RepositoriesMode.FAIL_ON_PROJECT_REPOS` means NO `allprojects { repositories {} }` in root build.gradle.kts
- ⚠️ **libtermux is NOT on JitPack (as of 2026-07):** `com.github.libtermux:libtermux-android:1.0.0` returns 404 (pom missing) or 401 from JitPack. Adding it breaks `assembleDebug` with "Could not find com.github.libtermux...". The GitHub repo `libtermux/libtermux-android` exists (Apache-2.0, experimental, no tags/releases) but has NOT published artifacts. **Do NOT add the dependency until it's actually published.** Re-check availability before re-adding:
  ```bash
  curl -sI https://jitpack.io/com/github/libtermux/libtermux-android/1.0.0/libtermux-android-1.0.0.pom | head -1
  ```

### 1b. Chaquopy (THE permanent embedded-Python solution)

**Chaquopy 17.0.0** is the runtime to use — published, stable, AGP 9.0–9.2 compatible (verified against this project's AGP 9.0.1 / Gradle 9.6.1 / Kotlin 2.4.10). Python interpreter + pip packages get bundled inside the APK and run via JNI. Kotlin calls Python functions directly — no HTTP server, no Termux app, no libtermux dependency.

Setup:
```kotlin
// root build.gradle.kts
plugins {
    id("com.chaquo.python") version "17.0.0" apply false
}

// app/build.gradle.kts
plugins { id("com.chaquo.python") }
android {
    defaultConfig {
        ndk { abiFilters += listOf("arm64-v8a", "armeabi-v7a", "x86_64") }
        // arm64-v8a = modern phones, armeabi-v7a = old, x86_64 = emulators
    }
}
chaquopy {
    defaultConfig { version = "3.11" }   // build-time Python version
    sourceSets { getByName("main") { srcDir("src/main/python") } }
}
```
- Python code lives in `app/src/main/python/hermes_agent.py` (NOT under assets/ — that was the old layout; Chaquopy bundles from `src/main/python`).
- **Pitfall — skills folder must be at `app/src/main/python/skills/*.md`:** after moving from the old `assets/skills/` layout, if the `python/skills/` dir is never created, `get_status()` reports `skills: 0` and `list_skills()` returns `[]`. The engine's system prompt then has no skill context. Create the folder + at least one `.md` per skill (engine appends "Available Skills:" to its system prompt). `.md` files are NOT caught by the `*.py` gitignore trap, but verify with `git status` after `git add -A`.
- Kotlin side (`EngineManager.kt`):
  ```kotlin
  import com.chaquo.python.Python
  import com.chaquo.python.android.AndroidPlatform
  import org.json.JSONObject

  if (!Python.isStarted()) Python.start(AndroidPlatform(context))
  val module = Python.getInstance().getModule("hermes_agent")
  val reply = module.callAttr("process_chat", message).get("response").toString()
  ```
- **⚠️ Pitfall — PyObject field access is UNRELIABLE on device: use a JSON-string round-trip for status.** `module.callAttr("get_status")` returns a PyObject, and `status.get("tools").toString()` mis-parses on the emulator/phone: EngineManager logged `Engine ready: Python null, 1 tools` even though the engine was fully working (8 tools / 3 skills, chat + vision both fine). Root cause: Chaquopy's PyObject→Java conversion of nested lists is inconsistent. Fix (both sides):
  ```python
  # hermes_agent.py — add a JSON-string variant
  def get_status_json():
      return json.dumps(get_status())
  ```
  ```kotlin
  // EngineManager.kt — parse JSON instead of PyObject fields
  val statusJson = module.callAttr("get_status_json").toString()
  val status = org.json.JSONObject(statusJson)
  val toolsArr = status.optJSONArray("tools") ?: JSONArray()
  // ...optString/optInt per field; log "Engine ready: Python X, N tools, M skills"
  ```
  Verify locally before pushing (`hermes_agent.get_status_json()` must parse and carry tools/skills/python) — this exact bug surfaces as a wrong-but-harmless log line, so grep the log after install, don't trust the engine works from the log alone.
- Engine functions used by Kotlin: `process_chat(message)`, `run_tool(name, args, kwargs)`, `list_tools()`, `list_skills()`, `get_status()`, `get_status_json()`, `set_model(name)`, `clear_memory()`, `start_http_server(port)` (optional external client).
- **Pitfall — build needs a real Python on the build machine:** CI runners don't have Python by default. Error: `Couldn't find Python 3.11` / `Starting an external process ... during configuration time is unsupported`. Fix: add `actions/setup-python@v5` with `python-version: '3.11'` to EVERY Gradle job in the workflow (ktlint job too if it runs gradlew — Chaquopy plugin configures during any gradle invocation). This bites per-job: all 6 jobs needed it.
- **Pitfall — `ndk.abiFilters` is REQUIRED:** without it, configure fails with `Variant 'debug': Chaquopy requires ndk.abiFilters`. Add the abiFilters block shown above.
- **Pitfall — Gradle configuration cache MUST be disabled:** `gradle.properties` has `org.gradle.configuration-cache=true` by default in this repo. Chaquopy spawns Python during configuration time, which config-cache forbids → `Configuration cache state could not be cached: field 'sitePackages$delegate'` + `Starting an external process ... during configuration time is unsupported`. Fix in `gradle.properties`:
  ```
  org.gradle.configuration-cache=false
  ```
  (Keep `org.gradle.caching=true` — that's the build cache, different feature, safe.)

### 2. Android Manifest Permissions

Required permissions for phone control:
```xml
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.CAMERA" />
<uses-permission android:name="android.permission.SEND_SMS" />
<uses-permission android:name="android.permission.CALL_PHONE" />
<uses-permission android:name="android.permission.READ_SMS" />
<uses-permission android:name="android.permission.READ_CONTACTS" />
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
<uses-permission android:name="android.permission.MANAGE_EXTERNAL_STORAGE" />
<uses-permission android:name="android.permission.REQUEST_INSTALL_PACKAGES" />
<uses-permission android:name="android.permission.FOREGROUND_SERVICE_DATA_SYNC" />
```

### 3. Foreground Service

Create `HermesEngineService.kt`:
- Extends `Service`, uses `startForeground()` with notification
- Manages engine lifecycle (init → install deps → start LocalBridge → start Python engine → ready)
- Use `ACTION_START` / `ACTION_STOP` pattern
- Create notification channel in `onCreate()`

### 4. EngineManager.kt

Manages:
- libtermux bootstrap (Linux env in app's private storage)
- Node.js LocalBridge (port 4000) — proxy to OpenCode Zen API
- Python Hermes Engine (port 5000) — web search, fetch, tools, skills, memory
- Fallback simple HTTP proxy if server.mjs not found (pure Python)

### 5. Python Engine (assets/engine/python/hermes_agent.py)

Built-in tools:
- `web_search` — DuckDuckGo Lite (regex parsing, NOT htmlparser2). ⚠️ NEVER use an Android/mobile UA — DDG serves a stripped page with 0 results; desktop/plain `Mozilla/5.0` only. See `references/duckduckgo-search-fix.md`.
- `web_fetch` — HTTP URL fetch (5KB limit)
- `read_file` / `write_file` / `list_files` — Android storage
- `run_command` — shell via `subprocess`
- Memory via SQLite
- Skills loader — reads `*.md` from `app/src/main/python/skills/` (NOT assets/ — see pitfall below)

**⚠️ .gitignore trap:** this repo's `.gitignore` contains `*.py`, which silently excludes `hermes_agent.py` from `git add -A`. Result: file exists locally but never reaches GitHub → EngineManager's `startPythonEngine()` no-ops because the file check fails. Always force-add:
```bash
git add -f app/src/main/assets/engine/python/hermes_agent.py
git status --short   # verify it's staged as 'A' before committing
```

### 6. Node.js LocalBridge (assets/engine/localbridge/server.mjs)

- Port 4000, listens on 127.0.0.1
- Proxies to `opencode.ai/zen/v1/chat/completions`
- Default model: `opencode/mimo-v2.5-free`
- API key: `aetherix-master-7x9k2m4p`
- CORS headers enabled

### 7. GitHub Actions CI

```yaml
# .github/workflows/build.yml
# uses: actions/checkout@v4, actions/setup-java@v4 (JDK 21 Zulu)
# android-actions/setup-android@v3, then ./gradlew assembleDebug
# Upload artifact via actions/upload-artifact@v4
```

**Known issue:** Pushing `.github/workflows/*.yml` files requires `workflow` OAuth scope. If token lacks it to push, create workflow file via GitHub web UI instead. Full playbook (device-code login, scope refresh, web-UI fallback, force-push cleanup): `references/github-workflow-scope-device-login.md`.

### 8. MainActivity Modification

Override `onCreate()` to call `startHermesEngine()`:
```kotlin
private fun startHermesEngine() {
    val intent = Intent(this, HermesEngineService::class.java).apply {
        action = HermesEngineService.ACTION_START
    }
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
        startForegroundService(intent)
    else
        startService(intent)
}
```

## File Structure (New/Modified)

```
app/src/main/java/com/m57/hermescontrol/
├── service/
│   ├── HermesEngineService.kt    (foreground lifecycle)
│   └── EngineManager.kt          (engine bootstrap)
├── tools/
│   ├── WebSearchTool.kt          (optional Kotlin override)
│   └── PhoneTools.kt             (SMS, Call, Camera)
├── engine/
│   └── SkillsDatabase.kt         (320 skills store)
assets/engine/
├── localbridge/server.mjs        (Node.js proxy — legacy; Kotlin calls model directly now)
python/
├── hermes_agent.py               (Python engine — Chaquopy bundles from src/main/python)
├── hermes_gateway.py             (on-device WebSocket gateway, port 9119)
├── requirements.txt
└── skills/*.md                   (skill files → engine system prompt)
```

## Verification Checklist

- [ ] Root build.gradle.kts has NO `allprojects` block
- [ ] settings.gradle.kts has `maven("https://jitpack.io")` in dependencyResolutionManagement
- [ ] libtermux dependency ONLY if confirmed published on JitPack (check with curl first)
- [ ] All permissions in AndroidManifest.xml
- [ ] Foreground service declared in manifest
- [ ] Python engine syntax valid AND force-added (`git add -f`, .gitignore has `*.py`)
- [ ] MainActivity has startHermesEngine()
- [ ] GitHub Actions workflow file present (created via web if token lacks workflow scope)

## Workflow: Fix-All-Then-Push (User Preference, 2026-08)

This user (new to coding) gets frustrated by one-fix-per-push cycles: "fir se fail tu ek ek kerke bug fix fir deeply check fir push" — i.e. DON'T push after each individual fix. CI cycles are 6-8+ min each, and repeated red runs erode trust. Instead:

1. When a CI run fails, pull ALL failed-job logs FIRST (`gh run view --job=<id> --log-failed` per failing job — ktlint, lint, unit tests each have their own job ID).
2. Fix EVERY error found across all jobs in one commit (style + lint + config together).
3. Run local static checks before pushing (brace balance, line length, `.gitignore` traps like `*.py`, stale-code grep for removed modules).
4. THEN push once and watch the single run.

**Pitfall — changing a `const val` default breaks unit tests:** when you change a shared constant (e.g. `ServerEndpoint.DEFAULT_BASE_URL` https→http), unit tests that assert the old value fail (`ServerEndpointTest` `DEFAULT_BASE_URL is https localhost 9119`, `Issue647ProfileUrlTest` `val loopback = "https://..."`). Grep the test tree for the old literal BEFORE pushing (`grep -rn "https://127.0.0.1" app/src/test/`), update every test asserting it, and commit code+test together. Other tests that merely *mock* the URL (MockK `every { ... } returns "https://..."`) are independent of the default — leave them alone; only tests asserting the seeded default break.
Also: verify downloads/APKs before telling the user they're ready (user asked "DOWNLOAD MAT ANDAR DEKH KUCH MASLA TO NAI" — verify contents before delivering), and test interpreter code locally before building (syntax check + smoke test — see `scripts/test_gateway_ws.py`).

### Page-by-page build + test-locally-first (User Preference, 2026-08)

User explicitly asked for **incremental page-by-page development** — build ONE screen/feature, test it, THEN move to the next ("EK EK PAGE KERKE APAN APP BUILD KERTE HE PEHLE EK PAGE KO SET KARENGE FIR TEST KARENGE FIR 2 PAGE FIR TEST"). Don't build the whole app then reveal it at the end — deliver a runnable slice first.

Companion preference: **test the engine on the PC first, not via phone/APK each time** ("ESA KUCH TOOL NAI HE KI APAN YAHI PER TEST KARE... TU YAHI KE YAHI TEST KARLE"). Because `hermes_agent.py` / `hermes_gateway.py` are pure Python, the SAME code that runs on-device can be smoke-tested locally (syntax check, `get_status()`, all 8 tools, WS gateway flow) BEFORE building any APK. This gives the user hands-on proof instantly and skips the slow APK→phone→test loop. Only build/install when the UI layer specifically needs verifying. Full tiered testing strategy (PC-local vs GitHub emulator vs VM — including why the GCP e2-small VM can't run an emulator): `references/phone-like-testing-strategy.md`.

Before a new screen/feature: explain in simple Hinglish what the page will do (flow + step-by-step), get a "karun" approval, then implement. When the user challenges "PC pe to sab chalta hai but phone me nai chalega", use the APK zip inspection above as proof, don't just assert.

## ktlint CI Pitfalls (EngineManager-style new files)

CI runs ktlint 1.2.1 (`ktlintCheck`) BEFORE the build — style errors fail the whole pipeline even when code compiles. Recurring violations in engine files:

- `standard:multiline-expression-wrapping` — a multiline expression (e.g. `Runtime.getRuntime().exec(...)` assigned to a val) must have the assignment break after `=`, then the call on the next line:
  ```kotlin
  val process =
      Runtime.getRuntime().exec(...)
  ```
  NOT `val process = Runtime...` with args wrapped.
- `standard:string-template-indent` — a raw `"""..."""` string (e.g. embedded Python in startSimpleProxy) must not be indented; the closing `"""` aligns with the raw content. Indenting the raw string body raises one error per line.
- `standard:trailing-comma-on-declaration-site` / `-on-call-site` — trailing comma required on the last param of every multi-line declaration AND call (including `enum class`, `data class`, `arrayOf(...)`).
- `standard:no-empty-first-line-in-class-body` — no blank line immediately after `class X {` / `companion object {`.
- `standard:spacing-between-declarations-with-annotations` — an annotated declaration (`@Volatile var x`, `@Composable fun`, etc.) needs a BLANK LINE between it and the PREVIOUS declaration. Pattern that fails:
  ```kotlin
  object X {
      @Volatile
      var a = null      // ❌ no blank line before this block's first annotation
      @Volatile         // ❌ no blank line between a and this annotation
      var b = null
  }
  ```
  Fix: blank line after `object X {` AND between every `@Volatile`-annotated declaration group.
- `standard:function-signature` — multi-line function params each on their own line, opening paren followed by newline.

If no JDK locally, run the ktlint binary (needs Java): `./ktlint --format <file>`. Otherwise fix per the rules above and let CI re-check — each push cycles CI ~6-8 min.

## Android Lint CI Pitfalls (Manifest)

`lintDebug` fails with **5 errors / 72 warnings** when phone-control permissions are added. The first (and usually only logged) failure:

```
AndroidManifest.xml:20: Error: Permission exists without corresponding hardware
<uses-feature android:name="android.hardware.telephony" required="false"> tag
[PermissionImpliesUnsupportedChromeOsHardware]
```

**Fix:** every permission that implies hardware needs a matching `<uses-feature>` with `required="false"` (so phones without the hardware can still install):
```xml
<uses-feature android:name="android.hardware.telephony" android:required="false" />
<uses-feature android:name="android.hardware.camera" android:required="false" />
<uses-feature android:name="android.hardware.location" android:required="false" />
```
`gh run view --log-failed` only shows the FIRST lint error — for the full list download the `lint-reports` artifact.

## Instrumented Tests CI — Emulator Boot Timeout

Common GitHub Actions failure that is NOT a code bug:
```
error: could not connect to TCP port 5554: Connection refused
Timeout waiting for emulator to boot.
```
Root cause: emulator (virtual phone) fails to boot on free runners — snapshot corruption or too-short boot wait. Fixes that worked:
- CI workflow: force **fresh AVD creation + `no-snapshot`** (don't reuse saved emulator state)
- Increase boot timeout / add retry on `connectedDebugAndroidTest`
- If the emulator job keeps failing while ALL other jobs (ktlint, lint, unit tests, build, release-compile) pass, treat it as environmental — the APK is still valid; CI Summary gates on it though, so a green "everything" run needs it fixed or removed from the gate.

## CI Summary Gate

The `ci-summary` job is an aggregator (`if: always()`). It fails whenever ANY upstream job fails — its own failure is never the root cause. Check the individual jobs first.

## Downloading the Built APK

```bash
# Artifact is named hermescontrol-debug-apk (contains app-debug.apk, ~28-33 MB)
gh run download <run-id> --repo <owner>/<repo> --name hermescontrol-debug-apk --dir <existing-dir>
```
Pitfall: `gh run download` **silently no-ops** (exit 0, nothing downloaded) if the `--dir` doesn't already exist. `mkdir` it first, or `cd` into the target dir and drop `--dir`. Verify with `ls -la` after — artifact download can take minutes.

**Fast path when the PC download stalls (≥5 min / times out at 300s):** download the artifact zip DIRECTLY on the GCP test VM — the VM's network to GitHub is far faster than the user's PC. Two ways:
1. gh CLI on the VM: `gh run download <run-id> --repo <owner>/<repo> --name hermescontrol-debug-apk` (works if gh is installed + authed there).
2. No gh on VM — curl with the PC's token, then unzip on the VM:
   ```bash
   # On the PC:
   GHTOKEN=$(gh auth token)
   ART_ID=$(gh api "repos/<owner>/<repo>/actions/artifacts?per_page=10" \
     --jq '.artifacts[] | select(.name=="hermescontrol-debug-apk") | .id' | head -1)
   # On the VM:
   curl -sL -o apk.zip -H "Authorization: Bearer $GHTOKEN" \
     -H "Accept: application/vnd.github+json" \
     "https://api.github.com/repos/<owner>/<repo>/actions/artifacts/$ART_ID/zip"
   unzip -o apk.zip -d apk_extract && ls -lh apk_extract/   # contains app-debug.apk
   ```
   Then `adb install /tmp/apk_extract/app-debug.apk` straight from the VM (the emulator is there too). Always confirm the extracted APK size matches the artifact's `size_in_bytes` before installing (a truncated zip → `INSTALL_PARSE_FAILED_NOT_APK`).

## Multi-Agent Collaboration on the Same Repo

When another agent/assistant is also pushing to the same repo (common in this project — the user runs several agents on one repo):
- Always `git pull --rebase` before pushing; plain push fails with "fetch first" hints.
- `git fetch origin && git log --oneline origin/main -3` to see what the other agent did BEFORE rebasing.
- Rebase conflicts from style-only differences: resolve with `git checkout --theirs <file>` (keep the other agent's version) then `git rebase --continue`, then `GIT_EDITOR=true git rebase --continue` to skip the editor.
- ⚠️ Force-push (`git push --force`) wipes web-UI-created files (e.g. a workflow file the user added manually). After any force-push, re-verify `.github/workflows/` still exists on the remote via `gh api repos/<owner>/<repo>/contents/.github/workflows`.
- ⚠️ **NEVER `git rm --cached` a workflow file just to split it out of a commit.** The staged deletion rides into the NEXT commit and deletes the workflow from the remote entirely (CI silently stops running). If you need to exclude a workflow file from a push (token lacks `workflow` scope), instead: commit the code changes first WITHOUT touching the workflow file, then handle the workflow file separately (web UI or a token with workflow scope). After any commit that touches `.github/workflows/`, verify with `gh api .../contents/.github/workflows` that all expected workflow files still exist on the remote.
- Compare local vs remote state: `git ls-files <path>` (staged), `gh api .../contents/<path>` (remote). A file "missing on GitHub but present locally" usually means .gitignore (see `*.py` trap) or a failed push.

## Prove Python Is Bundled (APK zip inspection) — user challenge "PC works, phone won't"

The user cares that "PC runs it because Python is installed, but the phone has no Python, so it won't run." Don't *assert* Chaquopy bundles Python — **prove it against the built APK**: the APK roughly doubles in size (this project went ~33 MB → ~71 MB) and the zip must contain a real CPython:

```python
import zipfile
apk = zipfile.ZipFile("app-debug.apk")
names = apk.namelist()
# 1) Native interpreter per-ABI
#    lib/arm64-v8a/libpython3.11.so  (also armeabi-v7a, x86_64)
#    lib/arm64-v8a/libchaquopy_java.so
interp = any("/libpython" in n for n in names)
# 2) Python stdlib + pip requirements (.imy = Chaquopy compressed bundle)
stdlib  = any("chaquopy/stdlib-" in n for n in names)
reqs    = any("chaquopy/requirements" in n for n in names)
# 3) app code (hermes_agent.py, hermes_gateway.py) is compiled into
#    assets/chaquopy/app.imy  (NOT a raw .py — Chaquopy compiles it)
app_code = any("chaquopy/app.imy" in n for n in names)
```

If all three present, Python runs on-device. This is the concrete proof to give the user (plus "same hermes_agent.py tested on PC = same code, only the interpreter location differs"). Note the `.py` files do NOT appear as raw files in the APK — they're compiled into `app.imy`.

## APK Binary Verification (Without Android SDK)

After building, verify the APK without needing a local Android SDK:

```python
import zipfile, re

apk = zipfile.ZipFile("app-debug.apk")
manifest = apk.read("AndroidManifest.xml")

# AXML is binary UTF-16; search with both encodings
for perm in ["android.permission.SEND_SMS", "android.permission.CAMERA", ...]:
    found = perm.encode() in manifest or perm.encode("utf-16-le") in manifest
    print(('✅' if found else '❌'), perm.split('.')[-1])

# Check compiled classes exist in dex files
with apk:
    for name in apk.namelist():
        if name.endswith('.dex'):
            content = apk.read(name)
            if b'HermesEngineService' in content:
                print("✅ HermesEngineService compiled")
```

## Runtime = THE Fundamental Blocker (RESOLVED via Chaquopy)

Both P1 (LocalBridge/brain) and P2 (Python engine/MCP) need a runtime (Python/Node.js) on Android. **The permanent answer is Chaquopy** (see section 1b) — it bundles a real CPython interpreter in the APK. Architecture adopted:

1. **Drop Node.js entirely** — Kotlin calls the model API directly via OkHttp (no LocalBridge process needed on the phone; `EngineManager.chat()` goes straight to OpenCode Zen). This halves the runtime dependency and removes the "node: not found" failure mode on stock Android.
2. **Python via Chaquopy** — `hermes_agent.py` (tools, skills, memory, LLM client) runs in-process; Kotlin calls functions directly through `Python.getInstance().getModule("hermes_agent")`.

Rejected paths (historical): libtermux (not published to JitPack), Termux app pairing (user wants single-APK), bundled static binaries (larger APK, more work).

## Gateway Port Architecture (Clear Map)

```
App (Kotlin UI) ←→ Port 9119 (Gateway REST+WebSocket)  ← External-facing
                       ↕
EngineManager (internal) ←→ Port 4000 (LocalBridge/brain/model proxy)
                          ←→ Port 5000 (Python MCP/tools)
```

The app connects to port 9119 only. The internal ports (4000/5000) are not directly reachable from outside the app. The Gateway layer bridges from 9119 to the internal services. Without a gateway process at 9119, the app shows "Dashboard unreachable".

**Note for the embedded-Chaquopy build:** since Kotlin calls Python in-process, the 4000/5000 ports become optional (only needed if you want external HTTP clients). The remaining external requirement is port 9119 for the app UI — plan a small on-device gateway (Python `start_http_server` or a Kotlin Ktor/NanoHTTPD server) bound to 127.0.0.1:9119 so the app connects to localhost and needs no VM/PC.

**✅ RESOLVED (2026-08):** the on-device gateway exists as `app/src/main/python/hermes_gateway.py` (~345 lines, pure Python stdlib + `websockets` lib). It speaks the Hermes TUI JSON-RPC 2.0 protocol on `ws://127.0.0.1:9119/api/ws` and also serves REST probe endpoints the app hits before connecting WS:
- `GET /api/status` → `{"status":"ok","auth_required":false,...}` (AuthLoginViewModel probe)
- `GET /api/health` → `{"status":"ok"}` (dashboard health check)
- `GET /` → HTML embedding `window.__HERMES_SESSION_TOKEN__ = "..."` (loopback login auto-populate)
- WS methods: `session.list/create/resume/status/history`, `commands.catalog`, `prompt.submit` (streams `message.start/delta/complete/done` events then returns RPC result), `session.interrupt`

**Model picker gap (found via emulator, 2026-08):** the Chat screen's "Model" button opens a picker that calls `GET /api/model/options` (see `HermesApiService.getModelOptions()` → `ModelOptionsResponse(providers: [...])`). The embedded gateway does NOT serve this endpoint, so the picker shows **"No models available."** even though the engine supports `set_model(name)` and the 7 free Zen models (`mimo-v2.5-free`, `deepseek-v4-flash-free`, etc.) exist. To make in-app model switching work, add `GET /api/model/options` to `hermes_gateway.py` returning at least `{"providers":[{"slug":"opencode","name":"OpenCode Zen","is_current":true,"models":["mimo-v2.5-free",...]}]}`. Without it, users can only use the configured `DEFAULT_MODEL`.

EngineManager starts it via Chaquopy: `py.getModule("hermes_gateway").callAttr("start_gateway_background")` — wrapped in try/catch so a gateway failure is non-fatal to the engine. Requires `websockets>=12.0` in the Chaquopy pip requirements.

**Local gateway smoke test (run on PC before building APK):** `pip install websockets`, then run `python app/src/main/python/hermes_gateway.py` in background, then:
- `curl http://127.0.0.1:9119/api/status` + `/api/health` + `/` (all 3 must return the payloads above)
- WS JSON-RPC flow: connect with `?token=hermes-mobile-token`, expect `gateway.ready` event, then `session.create` → `prompt.submit` with a trivial message → collect `message.start → delta → complete → done`. A live LLM reply (via OpenCode Zen from the embedded `hermes_agent.LLMClient`) confirms the whole chain works end-to-end. Ready-made script: `scripts/test_gateway_ws.py`.

**⚠️ Scheme mismatch bug (found via emulator test, 2026-08):** the embedded gateway serves **cleartext HTTP** on 9119, but the app's `ServerEndpoint.DEFAULT_BASE_URL` was hardcoded `https://127.0.0.1:9119/`. Symptom: AuthLogin probe hangs on "Probing dashboard…" forever (SSL handshake to a plain-HTTP socket) — this was ALSO the "Dashboard unreachable" on the real phone earlier. Fix: `DEFAULT_BASE_URL = "http://127.0.0.1:9119/"`. Verified safe for this app: `parse()` accepts both schemes, WebSocket scheme derives from URL (`http` → `ws://`), and `ALLOW_CLEARTEXT=true` in both build types + `network_security_config.xml` `cleartextTrafficPermitted="true"` means `parseForBuild` (used by probe) allows HTTP. If you ever harden the gateway with TLS later, flip the default back — but keep the two in sync. Always verify with `adb shell "ss -tlnp" | grep 9119` (LISTEN with app uid) + `adb logcat | grep EngineManager` that the on-device gateway is actually up before blaming the URL.

## Vision / Multimodal (images → model) — ADDED 2026-08

The embedded engine supports sending images to the model. Two attachment paths, both merge into OpenAI-style multimodal content:

- **`@file:/path` refs in the message text** — `_build_user_content()` (in `hermes_agent.py`) regex-extracts `@file:(\S+)`, loads image files (ext in `_IMAGE_EXTENSIONS` = .png/.jpg/.jpeg/.gif/.webp/.bmp) as base64 data-URIs, and returns a content array `[{"type":"text","text":...},{"type":"image_url","image_url":{"url":"data:<mime>;base64,..."}}]`. Non-image refs are ignored; missing files become a `[Image not found: ref]` text part.
- **Gateway-staged images** — the app's ChatViewModel sends RPC `image.attach_bytes` (see `WsMethods.IMAGE_ATTACH_BYTES`) with params `session_id`, `content_base64` (a full `data:<mime>;base64,....` URI), `filename`, `ext`. The gateway handler `handle_image_attach_bytes` stores them on the session (`sess["images"]`), then `handle_prompt_submit` drains them into `process_chat(text, 20, data_uris)` and CLEARS the session list so images don't leak into the next message. `process_chat` accepts `images=None` (list of data-URIs) and merges them into the content parts.

Key wiring facts:
- `image.attach_bytes` must be registered in `_HANDLERS` as a SYNC handler (takes `params` only, no `ws`) — non-prompt handlers run via `asyncio.to_thread(handler, rpc_params)`. `session.interrupt` must stay `async` (it's awaited directly).
- Do NOT mix: the app-side WS flow already worked for text; vision needs the gateway to pass staged data-URIs explicitly — the `@file:` filesystem path does not exist on-device for gallery picks.
- Verified live with `mimo-v2.5-free` (vision-capable): red PNG → "Red", blue PNG → "Blue" through both paths.
- Model identity: `get_status()["model"]` reports the configured `DEFAULT_MODEL` (`mimo-v2.5-free` via `ZEN_DEFAULT_MODEL` env); replies carry `model` in `message.complete` payload. In-app switching is blocked until `GET /api/model/options` is served (see model-picker gap above).

Test recipe (tiny programmatic PNG — no image assets needed): build a 2×2 PNG with `struct.pack(">IIBBBBB",2,2,8,2,0,0,0)` IHDR + `zlib.compress` raw scanlines + CRC chunks, write to temp, then `ha._build_user_content(f"color? @file:{tmp}")` must return a list containing an `image_url` part. Full re-runnable probe: `scripts/test_vision.py` (also does gateway-wiring + live LLM checks). Full detail, code shapes, and every pitfall: `references/vision-multimodal.md`.

## Useful Reference Files

- `references/chaquopy-integration.md` — THE permanent runtime: full Chaquopy setup, Kotlin↔Python calling pattern, ndk.abiFilters + setup-python CI pitfalls, workflow-scope and git-staging accidents
- `references/duckduckgo-search-fix.md` — DDG search quirks: Node.js fetch vs curl, AND the Android-UA-strips-results trap (desktop UA only)
- `references/github-workflow-scope-device-login.md` — workflow-scope token issues, device-code login, web-UI fallback
- `references/android-ci-troubleshooting.md` — full error transcripts + fixes for the CI failure chain (JitPack, ktlint, lint, emulator, artifact download)
- `references/phone-like-testing-strategy.md` — where to run phone-like tests: PC-local Python (fastest), GitHub Actions emulator (free), and why the existing GCP e2-small VM CANNOT run an Android emulator (no KVM) while the NEW `hermes-test-lab` **N1-standard-2** instance (created with `--enable-nested-virtualization`) CAN — includes the Windows gcloud.cmd pitfalls (space-in-path mangles multi-word flags like `--min-cpu-platform="Intel Haswell"`; drop that flag).
- `references/emulator-on-vm-playbook.md` — END-TO-END playbook for actually running the APK on a headless emulator inside the GCP N1 test VM: SDK/cmdline-tools/AVD install, KVM permission fix (`usermod -aG kvm` + `chmod 666 /dev/kvm`, new SSH session required), `-no-window` emulator flags, adb install + launch, and the **KEY technique: reading the on-screen state via `adb shell uiautomator dump` (grep `text=`/`bounds=`) when the vision model can't see local screenshots** — plus confirming the on-device gateway is listening via `adb shell ss -tlnp | grep 9119`. See the https→http scheme bug it surfaced in the gateway section above. NEW (2026-08): driving the Chat UI headlessly requires tapping the Send button (`content-desc="Send"`) — `input keyevent 66` fills the field but does NOT send; and testing the on-device gateway from the host via `adb forward tcp:19119 tcp:9119` + SSH `-L` (prefer `adb forward` over `adb reverse` which hits "Address already in use"; run the ws client on the PC — the VM's apt `python3-websockets` 10.x crashes on Python 3.10 with the `loop parameter was removed from Lock()` TypeError). ALSO: first launch on a 2-core emulator often pops **"HermesMobile isn't responding"** while Chaquopy extracts Python — tap "Wait" (dialog bounds ~`[70,1300][1010,1426]`), then force-stop + relaunch once extraction is done; the engine log `Gateway started on port 9119` + `Engine ready: Python X, N tools` is the real success signal, and a `Session created` chat screen means the app connected.
- `references/vision-multimodal.md` — vision support in the embedded engine: `image.attach_bytes` RPC wiring, OpenAI multimodal content format, `@file:` ref handling, sync-vs-async handler pitfalls, tiny-PNG test generator, verified evidence
- `references/real-hermes-bundling.md` — upgrading from the mini engine to the FULL Hermes Agent (188 skills / 29+ tools): source anatomy, Chaquopy native-dep compatibility reality check, ~90%-achievable plan, and the user's "answer exactly what's asked" + "test everything then finalize" communication preferences