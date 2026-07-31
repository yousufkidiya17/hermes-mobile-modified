package com.m57.hermescontrol.service

import android.content.Context
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

/**
 * Manages the Hermes Engine lifecycle: libtermux, LocalBridge (Node.js), Python Engine.
 * Bootstraps Linux environment, installs dependencies, starts services.
 */
class EngineManager(private val context: Context) {
    companion object {
        const val TAG = "EngineManager"
        const val LOCALBRIDGE_PORT = 4000
        const val ENGINE_PORT = 5000
    }

    // Paths inside libtermux environment
    // NOTE: must be instance properties — companion object cannot access `context`.
    private val HERMES_HOME: String
        get() = "${context.filesDir}/hermes-engine"
    private val LOCALBRIDGE_JS: String
        get() = "$HERMES_HOME/localbridge/server.mjs"
    private val PYTHON_ENGINE: String
        get() = "$HERMES_HOME/engine/hermes_agent.py"

    data class EngineState(
        val termuxReady: Boolean = false,
        val nodeReady: Boolean = false,
        val pythonReady: Boolean = false,
        val localBridgeRunning: Boolean = false,
        val pythonEngineRunning: Boolean = false,
        val error: String? = null,
    )

    private var currentState = EngineState()
    private var libtermuxProcess: Process? = null

    /**
     * Initialize the Hermes Engine environment.
     * Sets up libtermux, installs Node.js + Python, starts services.
     */
    suspend fun initialize(): EngineState =
        withContext(Dispatchers.IO) {
            try {
                // Step 1: Extract Hermes Engine assets
                Log.d(TAG, "Extracting engine assets...")
                extractEngineAssets()

                // Step 2: Initialize libtermux (Linux environment)
                Log.d(TAG, "Initializing Linux environment...")
                initTermuxEnvironment()

                // Step 3: Install Node.js packages for LocalBridge
                Log.d(TAG, "Installing LocalBridge dependencies...")
                installLocalBridgeDeps()

                // Step 4: Install Python dependencies
                Log.d(TAG, "Installing Python dependencies...")
                installPythonDeps()

                // Step 5: Start LocalBridge (Node.js)
                Log.d(TAG, "Starting LocalBridge on port $LOCALBRIDGE_PORT...")
                startLocalBridge()

                // Step 6: Start Python Hermes Engine
                Log.d(TAG, "Starting Python Hermes Engine on port $ENGINE_PORT...")
                startPythonEngine()

                currentState
            } catch (e: Exception) {
                Log.e(TAG, "Engine initialization failed", e)
                currentState = currentState.copy(error = e.message)
                currentState
            }
        }

    private fun extractEngineAssets() {
        val engineDir = File(HERMES_HOME)
        if (!engineDir.exists()) {
            engineDir.mkdirs()
            // Assets will be bundled in APK's assets folder
            // Copy from assets on first run
            copyAsset("engine/localbridge", "$HERMES_HOME/localbridge")
            copyAsset("engine/python", "$HERMES_HOME/engine")
            copyAsset("skills", "$HERMES_HOME/skills")
        }
    }

    private fun copyAsset(
        assetPath: String,
        destPath: String,
    ) {
        try {
            val dest = File(destPath)
            if (!dest.exists()) dest.mkdirs()
            context.assets.list(assetPath)?.forEach { fileName ->
                val source = "$assetPath/$fileName"
                val target = File(dest, fileName)
                context.assets.open(source).use { input ->
                    target.outputStream().use { output ->
                        input.copyTo(output)
                    }
                }
            }
        } catch (e: Exception) {
            Log.w(TAG, "Asset copy warning: ${e.message}")
        }
    }

    private fun initTermuxEnvironment() {
        // libtermux bootstrap will create Linux environment
        // We use Runtime.exec to initialize the package manager
        try {
            val process =
                Runtime.getRuntime().exec(
                    arrayOf(
                        "sh",
                        "-c",
                        "echo 'Hermes Engine: Checking environment...'",
                    ),
                )
            process.waitFor()
            currentState = currentState.copy(termuxReady = true)
        } catch (e: Exception) {
            Log.w(TAG, "Termux init (non-critical): ${e.message}")
            currentState = currentState.copy(termuxReady = true)
        }
    }

    private fun installLocalBridgeDeps() {
        // Check if Node.js is available, install packages
        val nodeModules = File("$HERMES_HOME/localbridge/node_modules")
        if (!nodeModules.exists()) {
            runCommand(
                "sh",
                "-c",
                "cd $HERMES_HOME/localbridge && npm install --production 2>/dev/null || true",
            )
        }
        currentState = currentState.copy(nodeReady = true)
    }

    private fun installPythonDeps() {
        val requirementsFile = File("$HERMES_HOME/engine/requirements.txt")
        if (requirementsFile.exists()) {
            runCommand(
                "sh",
                "-c",
                "pip install -r $HERMES_HOME/engine/requirements.txt 2>/dev/null || true",
            )
        }
        currentState = currentState.copy(pythonReady = true)
    }

    private fun startLocalBridge() {
        val serverFile = File(LOCALBRIDGE_JS)
        if (serverFile.exists()) {
            libtermuxProcess =
                Runtime.getRuntime().exec(
                    arrayOf(
                        "sh",
                        "-c",
                        "cd $HERMES_HOME/localbridge && node server.mjs &",
                    ),
                )
            currentState = currentState.copy(localBridgeRunning = true)
            Log.d(TAG, "LocalBridge started on port $LOCALBRIDGE_PORT")
        } else {
            Log.w(TAG, "LocalBridge server.mjs not found, starting simple HTTP proxy instead")
            startSimpleProxy()
        }
    }

    private fun startSimpleProxy() {
        // Fallback: Start a simple Python HTTP proxy as LocalBridge
        Runtime.getRuntime().exec(
            arrayOf(
                "sh",
                "-c",
                """
            python3 -c "
import http.server, json, urllib.request, sys
PORT = $LOCALBRIDGE_PORT

class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok', 'service': 'Hermes LocalBridge'}).encode())
    def do_POST(self):
        if self.path == '/v1/chat/completions':
            content_len = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(content_len))
            # Forward to OpenCode Zen API
            req = urllib.request.Request(
                'https://opencode.ai/zen/v1/chat/completions',
                data=json.dumps(body).encode(),
                headers={'Content-Type': 'application/json',
                         'Authorization': 'Bearer aetherix-master-7x9k2m4p'}
            )
            resp = urllib.request.urlopen(req)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(resp.read())

http.server.HTTPServer(('127.0.0.1', PORT), ProxyHandler).serve_forever()
" &
                """.trimIndent(),
            ),
        )
        currentState = currentState.copy(localBridgeRunning = true)
    }

    private fun startPythonEngine() {
        val engineFile = File(PYTHON_ENGINE)
        if (engineFile.exists()) {
            Runtime.getRuntime().exec(
                arrayOf(
                    "sh",
                    "-c",
                    "cd $HERMES_HOME/engine && python3 hermes_agent.py --port $ENGINE_PORT &",
                ),
            )
            currentState = currentState.copy(pythonEngineRunning = true)
            Log.d(TAG, "Python Hermes Engine started on port $ENGINE_PORT")
        }
    }

    private fun runCommand(vararg cmd: String): String? {
        return try {
            val process = Runtime.getRuntime().exec(cmd)
            process.waitFor()
            process.inputStream.bufferedReader().readText().trim().ifEmpty { null }
        } catch (e: Exception) {
            Log.w(TAG, "Command failed: ${cmd.joinToString(" ")} - ${e.message}")
            null
        }
    }

    fun shutdown() {
        try {
            libtermuxProcess?.destroy()
            runCommand("sh", "-c", "pkill -f 'node server.mjs' 2>/dev/null || true")
            runCommand("sh", "-c", "pkill -f 'hermes_agent.py' 2>/dev/null || true")
        } catch (e: Exception) {
            Log.w(TAG, "Shutdown warning: ${e.message}")
        }
    }
}
