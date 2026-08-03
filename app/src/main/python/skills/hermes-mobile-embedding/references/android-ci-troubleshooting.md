# Android CI Troubleshooting — Hermes Mobile Modified (Session Notes)

Full failure chain observed while getting `hermes-mobile-modified` (fork of Hy4ri/hermes-mobile) to build green on GitHub Actions. Every failure below was hit and resolved in order.

## 1. JitPack repo placement (Gradle 9)

**Symptom:**
```
Build was configured to prefer settings repositories over project repositories
but repository 'MavenRepo' was added by build file 'build.gradle.kts'
```

**Cause:** AGP 9 / Gradle 9 uses `RepositoriesMode.FAIL_ON_PROJECT_REPOS` (set in settings.gradle.kts). An `allprojects { repositories { ... } }` block in root `build.gradle.kts` is now an error, not a warning.

**Fix:** Put ALL repositories (incl. JitPack) in `settings.gradle.kts` → `dependencyResolutionManagement` → `repositories`:
```kotlin
maven { url = uri("https://jitpack.io") }
```

## 2. libtermux dependency not published

**Symptom:**
```
Could not find com.github.libtermux:libtermux-android:1.0.0.
Searched: ... https://jitpack.io/com/github/libtermux/libtermux-android/1.0.0/... 401/404
```
Also `terminal-view` 401 Unauthorized from JitPack.

**Cause:** `libtermux/libtermux-android` exists on GitHub (Apache-2.0, experimental) but has NOT published artifacts to JitPack. Version `1.0.0` is claimed in its README but absent.

**Fix:** Remove both deps; EngineManager falls back to `Runtime.exec()` + a pure-Python proxy. Re-check before re-adding:
```bash
curl -sI https://jitpack.io/com/github/libtermux/libtermux-android/1.0.0/libtermux-android-1.0.0.pom | head -1
```

## 3. .gitignore `*.py` silently drops the Python engine

**Symptom:** `hermes_agent.py` exists locally, CI unit tests pass, but EngineManager's `startPythonEngine()` no-ops; other agents report "hermes_agent.py doesn't exist in repo". `gh api repos/<owner>/<repo>/contents/app/src/main/assets/engine/python` shows only `requirements.txt`.

**Cause:** repo `.gitignore` contains `*.py`. `git add -A` silently skips it.

**Fix:**
```bash
git add -f app/src/main/assets/engine/python/hermes_agent.py
git status --short   # must show 'A' before committing
```

## 4. ktlint style failures

CI job `ktlint — Code Style` runs `./gradlew ktlintCheck` (ktlint 1.2.1) BEFORE build. ~35 errors in `EngineManager.kt`:

- `standard:multiline-expression-wrapping` — assignment must break after `=`, call on next line:
  ```kotlin
  val process =
      Runtime.getRuntime().exec(
          arrayOf(...),
      )
  ```
- `standard:string-template-indent` — raw `"""..."""` body must not be indented (one error per line — the Python heredoc inside `startSimpleProxy` triggered ~30 errors). Align content flush with closing `"""`.
- `standard:trailing-comma-on-declaration-site` / `-on-call-site` — trailing comma on LAST item of every multiline declaration AND call, incl. `enum class` and `data class`.
- `standard:no-empty-first-line-in-class-body` — no blank line after `class X {`.
- `standard:function-signature` — multiline params each on own line.

**Note:** another agent's "48 errors auto-fixed" commit and a manual rewrite can conflict — resolve with `git checkout --theirs` (their version) since both target the same rules.

## 5. Android Lint — PermissionImpliesUnsupportedChromeOsHardware

**Symptom:** `lintDebug` fails, "Lint found 5 errors, 72 warnings". First (only logged) failure is `AndroidManifest.xml:20`.

**Fix:** `<uses-feature android:name="android.hardware.telephony|camera|location" android:required="false" />` matching each hardware-implying permission. `--log-failed` shows only the FIRST error; grab the `lint-reports` artifact for the full list.

## 6. Instrumented Tests — emulator won't boot

**Symptom:**
```
The process '.../platform-tools/adb' failed with exit code 1
error: could not connect to TCP port 5554: Connection refused
Timeout waiting for emulator to boot.
```
Not a code bug. Fix: fresh AVD creation, `no-snapshot` (don't reuse saved state), longer boot timeout / retry on `connectedDebugAndroidTest`.

## 7. CI Summary gate

`ci-summary` job fails whenever any upstream job fails — never the root cause. All of ktlint + lint + unit + build + release-compile green, instrumented red → CI Summary still red.

## 8. gh run download silent no-op

`gh run download <id> --repo X --name hermescontrol-debug-apk --dir <path>` returns exit 0 with NOTHING downloaded if `<path>` doesn't exist. `mkdir` first or `cd` into target dir and drop `--dir`. Artifact is `hermescontrol-debug-apk` containing `app-debug.apk` (~28–33 MB). Verify with `ls -la`; download can take several minutes.

## Useful gh commands

```bash
# latest runs
gh run list --repo <owner>/<repo> --limit 3
# job detail + exit status
gh run view <run-id> --repo <owner>/<repo>
# failed-step logs (only after run COMPLETES)
gh run view <run-id> --repo <owner>/<repo> --log-failed
# artifacts on a run
gh api repos/<owner>/<repo>/actions/runs/<run-id>/artifacts --jq '.artifacts[] | .name + " (" + (.size_in_bytes|tostring) + " bytes)"'
# remote file presence (vs local git ls-files)
gh api repos/<owner>/<repo>/contents/<path>
```
