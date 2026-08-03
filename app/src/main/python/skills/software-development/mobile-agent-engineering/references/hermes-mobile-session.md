# Session Reference: Hermes Mobile Embedded Agent Build

## Repository
- **Source**: Hy4ri/hermes-mobile (open source, Apache 2.0)
- **Fork**: yousufkidiya17/hermes-mobile-modified (private)
- **Modified files**: 11 files across build config, manifest, services, assets

## File Structure (New/Modified)

```
Modified:
├── settings.gradle.kts            → JitPack repo added to dependencyResolutionManagement (Gradle 9 FAIL_ON_PROJECT_REPOS)
├── app/build.gradle.kts           → libtermux deps added then REMOVED (artifact not published to JitPack)
├── app/src/main/AndroidManifest.xml → 10 new permissions + engine service
├── app/src/main/java/.../MainActivity.kt → auto-start engine on create

New:
├── app/src/main/java/.../service/HermesEngineService.kt   (4156 bytes)
├── app/src/main/java/.../service/EngineManager.kt         (8604 bytes)
├── assets/engine/python/hermes_agent.py                   (9291 bytes, 4 classes)
├── assets/engine/python/requirements.txt
├── assets/engine/localbridge/server.mjs                   (3024 bytes)
├── assets/skills/web-search.md
└── .github/workflows/build.yml   (not pushed — requires workflow token scope)
```

## Build Status
- Code pushed to GitHub ✅
- APK building requires GitHub Actions (workflow file needs `workflow` scope)
- **libtermux is NOT published to JitPack** (404/401) — dependency was removed; engine falls back to `Runtime` shell
- **hermes_agent.py was blocked by `.gitignore`'s `*.py` rule** — must `git add -f` and verify with `git ls-files`
- CI failures seen: ktlint style errors (EngineManager.kt), lint `PermissionImpliesUnsupportedChromeOsHardware` (manifest needs `<uses-feature>` tags), emulator boot timeout (infra, not code)
- Alternative: add workflow file manually via GitHub web UI, then check Actions tab

## GitHub Token Issue
OAuth token from `gh auth login` gets `gist, read:org, repo` scopes but NOT `workflow`. To push `.github/workflows/*` files via git, use:
1. `gh auth refresh -h github.com -s workflow` → device code flow (often times out under automation)
2. Or use a classic PAT with `repo` + `workflow` scopes
3. Or bypass: create workflow file manually on github.com web UI

## Architecture (per user decision)
- **MCP-style**: tools/skills/memory stay in Python (`hermes_agent.py`, :5000); Kotlin app is a thin client
- **Brain-first start order**: LocalBridge LLM proxy (:4000) starts BEFORE the Python tool server
- No Kotlin rewrite of tested Python tools

See `references/ci-build-debugging.md` for exact error strings, fixes, and the known-good workflow file.
