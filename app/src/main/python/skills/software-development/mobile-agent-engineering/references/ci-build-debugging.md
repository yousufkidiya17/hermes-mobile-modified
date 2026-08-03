# Android CI Build Debugging (GitHub Actions)

Session-proven error signatures and fixes for building a modified Hermes Mobile APK on GitHub Actions (no local Android SDK).

## Debugging loop (fast)

```bash
# list runs
gh run list --repo <owner>/<repo> --limit 5

# full status of a run (jobs + pass/fail)
gh run view <run-id> --repo <owner>/<repo>

# failed logs for a specific job (only after the WHOLE run finishes)
gh run view --job=<job-id> --repo <owner>/<repo> --log-failed

# filter for actionable lines
gh run view --job=<job-id> --repo <owner>/<repo> --log-failed | grep -E "\.kt|\.kts|Error:|error:"
```

Note: `--log-failed` returns "run is still in progress" until the entire run completes (incl. instrumented tests), even if the job you care about already failed. Sleep and retry.

## Error 1 — libtermux dependency unresolvable

```
Could not find com.github.libtermux:libtermux-android:1.0.0.
Searched: ... https://repo.maven.apache.org/maven2/... https://jitpack.io/... Received status code 401 from server: Unauthorized
```

**Root cause:** artifact is not actually published to JitPack (repo README advertises it, JitPack has nothing). Fix: remove the dependency; use `Runtime`/`ProcessBuilder` shell fallback. Check publish state first:

```bash
curl -sI "https://jitpack.io/com/github/libtermux/libtermux-android/1.0.0/libtermux-android-1.0.0.pom" | head -3   # 404 = not published
```

## Error 2 — Gradle 9 repo placement

```
Build was configured to prefer settings repositories over project repositories but repository 'MavenRepo' was added by build file 'build.gradle.kts'
```

**Root cause:** `dependencyResolutionManagement.repositoriesMode = FAIL_ON_PROJECT_REPOS` in settings.gradle.kts forbids `allprojects { repositories {} }` in root build.gradle.kts.
**Fix:** add repos inside `dependencyResolutionManagement.repositories` in settings.gradle.kts:

```kotlin
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google { ... }
        mavenCentral()
        maven { url = uri("https://jitpack.io") }   // <-- here
    }
}
```

## Error 3 — ktlint style failures

Typical failures on new Kotlin files (all from `./gradlew ktlintCheck`):

- `standard:no-empty-first-line-in-class-body` — blank line right after `class X {`
- `standard:trailing-comma-on-declaration-site` / `-on-call-site` — missing trailing comma in multi-line data class / enum / call
- `standard:multiline-expression-wrapping` — long expression must break onto its own line:
  ```kotlin
  // ❌
  libtermuxProcess = Runtime.getRuntime().exec(arrayOf("sh", "-c", "node server.mjs &"))
  // ✅
  libtermuxProcess =
      Runtime.getRuntime().exec(
          arrayOf(
              "sh",
              "-c",
              "node server.mjs &",
          ),
      )
  ```
- `standard:string-template-indent` — raw strings containing embedded Python: every line inside the `"""` must carry consistent indentation relative to the closing `"""`. Fix by re-indenting the Python block or moving it to an asset file (cleaner: keep Python in `assets/engine/python/`, don't inline it in Kotlin strings).

Auto-fix: download ktlint 1.2.1 binary, needs a JDK on the machine:
```bash
curl -sSLO https://github.com/pinterest/ktlint/releases/download/1.2.1/ktlint
chmod +x ktlint
./ktlint --format <file>
```

## Error 4 — Android Lint PermissionImpliesUnsupportedChromeOsHardware

```
app/src/main/AndroidManifest.xml:20: Error: Permission exists without corresponding hardware <uses-feature android:name="android.hardware.telephony" required="false"> tag
```

**Root cause:** phone-control permissions added without declaring the hardware.
**Fix:** add to manifest:

```xml
<uses-feature android:name="android.hardware.telephony" android:required="false" />
<uses-feature android:name="android.hardware.camera" android:required="false" />
<uses-feature android:name="android.hardware.location" android:required="false" />
<uses-feature android:name="android.hardware.microphone" android:required="false" />
```

## Error 5 — Instrumented tests: emulator won't boot

```
error: could not connect to TCP port 5554: Connection refused
##[error]Timeout waiting for emulator to boot.
```

**Root cause:** GitHub-hosted free runner infrastructure, not app code. Fix: re-run the workflow; optionally bump AVD boot timeout in the workflow. Don't burn time debugging app code for this one.

## Error 6 — workflow scope blocking workflow file push

```
! [remote rejected] main -> main (refusing to allow an OAuth App to create or update workflow `.github/workflows/build.yml` without `workflow` scope)
```

**Root cause:** OAuth token from `gh auth login` device flow has only `gist, read:org, repo`.
**Fixes:**
- `gh auth refresh -h github.com -s workflow,delete_repo` → requires device-code browser entry; often times out under automation (default 15-120s window). If user completes it, token gains `workflow`.
- Fallback that always works: user creates the file via GitHub web UI (repo → Add file → Create new file → `.github/workflows/build.yml`), content pasted from local copy.
- Caveat: workflow files created via web UI are lost if a later `git push --force` rewrites history — use fetch/rebase instead.

## Known-good workflow (build debug APK + upload artifact)

```yaml
name: Build Hermes Mobile Modified APK
on:
  push:
    branches: [ main ]
  workflow_dispatch:
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: 'zulu'
          java-version: 21
      - uses: android-actions/setup-android@v3
      - run: chmod +x gradlew
      - run: ./gradlew assembleDebug
      - uses: actions/upload-artifact@v4
        with:
          name: hermes-mobile-modified-debug
          path: app/build/outputs/apk/debug/*.apk
```

## Git hygiene when another agent is on the same repo

- Always `git fetch origin && git pull --rebase` before pushing — remote often moves (other agent or user web-UI commits).
- On rebase conflict: `git checkout --theirs <file>` keeps the remote version (they may have fixed the same file), then re-apply only your unique diff.
- Never `git push --force` on a shared branch — it erases the other agent's commits AND web-UI-created workflow files.
- Verify asset files actually reached GitHub: `gh api repos/<owner>/<repo>/contents/<path>` and check the file list (`.gitignore` can silently exclude them).
