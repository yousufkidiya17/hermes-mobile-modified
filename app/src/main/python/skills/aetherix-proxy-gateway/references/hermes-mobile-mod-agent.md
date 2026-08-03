# Hermes Mobile → Full Agent via MCP + libtermux

## Goal
Turn the Hermes Mobile Android app (`Hy4ri/hermes-mobile`, F-Droid `com.mobilefork.hermesagent`) into a standalone AI agent with terminal access, skills (320), tools, and local model proxy — no separate VM or desktop required.

## Architecture

```
Modified Hermes Mobile APK (single install)
│
├── libtermux-android (embedded Linux runtime)
│   ├── Python (runs MCP server with existing tools)
│   ├── Node.js (runs LocalBridge for model proxy)
│   └── Skills (320 text instruction files)
│
├── MCP Server (Python)
│   ├── Web Search (HTTP → DuckDuckGo)
│   ├── Web Fetch (HTTP → URL content)
│   ├── File Ops (Android SAF)
│   ├── Terminal (libtermux PTY)
│   └── Phone APIs (Android SDK - SMS, Call, Camera)
│
├── Hermes Gateway API (local)
│   ├── Skills management
│   ├── Session management
│   └── Tool execution
│
└── App UI (existing, modified)
    ├── Chat (existing)
    ├── Skills (existing - connects to local MCP)
    ├── Toolsets (existing - connects to local MCP)
    └── Terminal UI (libtermux widget)
```

## Key Library: libtermux-android

- **Repo:** `github.com/libtermux/libtermux-android`
- **License:** Apache 2.0 (free, commercial OK)
- **Description:** Embed a full Linux environment (Termux runtime) inside any Android app — no separate Termux install required.
- **Features:** Python, Node.js, Bash, pkg manager, streaming output, background service, terminal UI widget, multi-arch (arm64, x86_64, arm, x86)
- **Status:** Experimental (not production-ready yet, but actively developed)
- **Integration:** 1-line Gradle dependency via JitPack

## Why MCP (Model Context Protocol) Instead of Kotlin Rewrite

The Hermes Mobile app **already has MCP support** (`ui/mcp/McpServersScreen.kt`, data model `McpServer` with transport/url/command/args/env fields). This means:

```
✅ Tools stay in Python (same tested code from desktop)
✅ No Kotlin rewrite of web search, fetch, file ops, etc.
✅ Skills stay as text files (no conversion needed)
✅ App already knows how to connect to MCP servers
✅ Just need to start the MCP server locally via libtermux
✅ Zero re-testing of existing tool logic
```

## Setup Steps

### 1. Build Dependencies
Add to `app/build.gradle.kts`:
```kotlin
repositories {
    maven { url = uri("https://jitpack.io") }
}
dependencies {
    implementation("com.github.libtermux:libtermux-android:1.0.0")
    implementation("com.github.libtermux:terminal-view:1.0.0")
}
```

### 2. Start Services on App Launch
In `MainActivity.kt` or `Application.onCreate()`:
```kotlin
// Auto-start libtermux (Linux runtime)
val termux = LibTermux.create(this) {
    autoInstall = true
    logLevel = LogLevel.DEBUG
}

// Start LocalBridge (Node.js model proxy)
termux.runScript("node /data/local/tmp/server.mjs")

// Start MCP Server (Python tools)
termux.runScript("python /data/local/tmp/mcp_server.py")

// Auto-connect Hermes Gateway to these local services
```

### 3. Bundle Assets
Include in the APK:
- `server.mjs` (LocalBridge - Node.js proxy to OpenCode Zen API)
- `mcp_server.py` (MCP server with web search, fetch, tools)
- `skills/` directory (320 text instruction files)

### 4. Modify App Config
The app needs to connect to:
- **Model API:** `http://localhost:4000/v1` (LocalBridge)
- **MCP Server:** `http://localhost:9090` (or the port the Python MCP server listens on)
- **Phone APIs:** Direct Android SDK calls (SMS, Contacts, Camera, etc.)

## Limitations
- libtermux-android is experimental (v1.0.0, 9 GitHub stars)
- Full phone control (SMS, calls) requires Android permissions declared in manifest
- Terminal keyboard UX on mobile needs careful design
- ~3-4 sec cold start for libtermux bootstrap on first launch
- Model requires internet (LocalBridge → OpenCode Zen API via HTTP)

## Alternative: Keep Using VM
If libtermux proves unstable, the fallback is keeping Hermes on a cheap GCP e2-micro/e2-small VM and connecting the mobile app to it. The VM approach is battle-tested in this project but costs ~$7/mo and needs internet on the phone.

## References
- libtermux-android: https://github.com/libtermux/libtermux-android
- Hermes Mobile source: https://github.com/Hy4ri/hermes-mobile
- Hermes Mobile F-Droid: https://f-droid.org/packages/com.mobilefork.hermesagent/
- MCP Protocol: https://modelcontextprotocol.io/
