# Chaquopy Integration — Embedded Python for Hermes Mobile (2026-08)

Adopted 2026-08-01 as the PERMANENT runtime after libtermux turned out to be
unpublished. This supersedes the "wait for libtermux" plan.

## Why Chaquopy

| Aspect | libtermux | Chaquopy |
|---|---|---|
| Published to Maven/JitPack | ❌ (404/401, no tags) | ✅ v17.0.0 on Gradle Plugin Portal |
| AGP 9.0 support | ❓ | ✅ v17.0.0: "Android Gradle plugin versions 9.0 to 9.2 are now supported" |
| Python runtime | Needs Termux-style bootstrap | ✅ Real CPython interpreter bundled in APK (3.8–3.13) |
| Kotlin interop | subprocess/HTTP | ✅ Direct JNI calls (`Python.getInstance().getModule(...)`) |
| Single-APK | ❌ needs Termux app | ✅ fully embedded |

Check latest version + AGP compat:
```bash
curl -sL "https://plugins.gradle.org/m2/com/chaquo/python/com.chaquo.python.gradle.plugin/maven-metadata.xml" -H "User-Agent: Mozilla/5.0" | grep -oE "<version>[^<]+</version>" | tail -5
curl -sL "https://chaquo.com/chaquopy/doc/current/changelog.html" -H "User-Agent: Mozilla/5.0" | grep -oE "Android Gradle plugin versions [0-9.]+ to [0-9.]+"
```

## Gradle Setup (Kotlin DSL)

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
    }
}

chaquopy {
    defaultConfig { version = "3.11" }
    sourceSets { getByName("main") { srcDir("src/main/python") } }
}
```

Python source directory: `app/src/main/python/hermes_agent.py` (Chaquopy convention).

## Kotlin → Python Calling Pattern

```kotlin
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

if (!Python.isStarted()) {
    Python.start(AndroidPlatform(context))   // MUST be on a started context
}
val module = Python.getInstance().getModule("hermes_agent")
val status = module.callAttr("get_status")      // returns PyObject
status.get("tools").toString()
status.get("python").toString()

val reply = module.callAttr("process_chat", userMessage)
reply.get("response").toString()
```

## Pitfall 1: ndk.abiFilters is REQUIRED

Without it, every Gradle task fails at configuration:
```
> Variant 'debug': Chaquopy requires ndk.abiFilters: you may want to add it to android.defaultConfig.
```
Fix: the `ndk { abiFilters += ... }` block above. All three ABIs (arm64-v8a,
armeabi-v7a, x86_64) so emulators (x86_64) and old/new phones all install.

## Pitfall 2: CI runners need Python installed

Chaquopy runs a `check_build_python.py 3.11` external process during
configuration. GitHub Actions ubuntu runners do NOT have Python 3.11 on PATH
(they have 3.12+ system python) → error:
```
Couldn't find Python 3.11. See .../android.html#buildpython
Starting an external process '/usr/bin/python3 ... check_build_python.py 3.11'
during configuration time is unsupported.
```
Fix: add setup-python to EVERY Gradle job (ktlint job too — it runs gradlew):
```yaml
- name: Set up Python 3.11 (Chaquopy build requirement)
  uses: actions/setup-python@v5
  with:
    python-version: '3.11'
```
The android.yml workflow has 6 Gradle jobs — all 6 needed this step.

## Pitfall 3: workflow scope blocks workflow pushes

Same as before: OAuth token without `workflow` scope cannot push
`.github/workflows/*.yml` ("refusing to allow an OAuth App to create or update
workflow ... without `workflow` scope"). Workflow file changes must go through
the GitHub web UI (Add file → Create new file → paste content) until the token
is refreshed with `gh auth refresh -h github.com -s workflow`.

## Pitfall 4: NEVER `git rm --cached` a workflow file to split a commit

This session's accident: reset a commit, ran `git rm --cached
.github/workflows/android.yml` intending to keep it local-only — the staged
deletion committed with the next push and REMOVED android.yml from the remote.
CI for the repo silently stopped (no workflow = no runs). Recovery was manual
re-creation via web UI. Correct approach: leave the workflow file untouched and
out of the commit entirely; commit only code changes.

## hermes_agent.py engine API (used by EngineManager)

- `process_chat(message, history_limit=20)` → `{"response": str, "model": str}`
- `run_tool(name, args=[], kwargs={})` → `{"ok": bool, "result": ...|"error": str}`
- `list_tools()` / `list_skills()` / `get_status()` / `set_model(name)` / `clear_memory()`
- `start_http_server(port=5000)` — optional, for external HTTP clients only
- LLM client: direct `urllib.request` to `https://opencode.ai/zen/v1/chat/completions`,
  model `opencode/mimo-v2.5-free`, key `aetherix-master-7x9k2m4p` (no pip deps —
  stdlib only, so `pip {}` block is empty in chaquopy config)

## Status check after integrating

```bash
# local: engine files in right place
ls app/src/main/python/
# CI green
gh run list --repo <owner>/<repo> --limit 3
# APK contains python + engine
unzip -l app-debug.apk | grep -iE "python|hermes_agent|libpython"
```
