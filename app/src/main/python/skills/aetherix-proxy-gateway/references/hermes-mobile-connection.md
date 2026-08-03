# Hermes Mobile App → Gateway Connection

## Overview

The Hermes Mobile Android app (`com.m57.hermescontrol`) connects to a Hermes Gateway REST API, not directly to an OpenAI-compatible endpoint. Connecting it directly to LocalBridge:4000 gives only chat — no skills, tools, memory, or agent capabilities.

## Source & F-Droid

- **GitHub:** `Hy4ri/hermes-mobile` — Kotlin + Jetpack Compose, Apache 2.0
- **F-Droid:** `com.mobilefork.hermesagent` (a fork)
- **Latest version:** v1.19.2 (July 2026)
- **Current package:** `com.m57.hermescontrol`

## Architecture (How Connection Works)

```
Hermes Mobile App (Android)
    │
    ├── Connects to → Hermes Gateway REST API (default port 9119)
    │                  └── Full agent: skills, tools, memory, cron, models
    │
    └── ALSO supports → OpenAI-compatible API (LocalBridge:4000)
                         └── Only chat, no agent features
```

### Connection Config
The app stores profiles in `ConnectionProfile.kt`:
```kotlin
data class ConnectionProfile(
    val id: String,
    val name: String,
    val baseUrl: String? = null,  // Gateway URL like "http://192.168.1.100:9119"
)
```

## Key Files in Source

| File | Purpose |
|------|---------|
| `data/config/ConnectionProfile.kt` | Connection profile data model |
| `data/remote/HermesApiService.kt` | Retrofit API client (talks to Gateway) |
| `data/remote/ApiClient.kt` | HTTP client setup with auth |
| `data/config/ServerCollectionOps.kt` | Profile management list |

## How Skills/Tools Work

The app **already supports skills & tools management through the Gateway API**. Features from the README:
- "Manage active profiles, installed skills, plugins, toolsets, and LLM model/provider selections"
- "Message your agent with full context"
- Cron job management
- Model switching

## To Get Full Agent on Mobile

**Do NOT** connect the mobile app directly to LocalBridge:4000. Instead:
1. Make the Hermes Gateway accessible (default port 9119, but depends on config)
2. Open the gateway's REST API port in the firewall
3. Connect the mobile app to `http://VM_IP:PORT` (the gateway URL)
4. Authenticate via pairing or token

## Mobile App Modification (Custom Build)

To modify and build a custom version:
1. Clone `Hy4ri/hermes-mobile`
2. Edit Kotlin source in `app/`
3. Build APK via:
   - **Local:** Android Studio / Gradle
   - **CI:** GitHub Actions (free) — push to repo with `.github/workflows/` build workflow
   - **VM:** Install Android SDK + Gradle
4. The app uses Gradle build system with Kotlin DSL

## Pitfalls

- The app stores connection profiles locally in Room DB
- Default port in code is 9119 (legacy loopback)
- The app expects a Hermes Gateway, not a plain OpenAI API
- Building requires Android SDK API 26+ (minSdk) to 36 (targetSdk)
- Node.js v18 fetch on GCP fails for DuckDuckGo — use curl for search (see main skill)
