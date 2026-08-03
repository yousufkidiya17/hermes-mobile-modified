package com.m57.hermescontrol.service

import android.content.Context
import android.util.Log
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray

/**
 * Manages the embedded Hermes Engine via Chaquopy (bundled Python in APK).
 * Python interpreter runs on-device via JNI — no Termux app, no libtermux.
 * Kotlin calls Python functions directly through Chaquopy's Python API.
 */
class EngineManager(private val context: Context) {
    companion object {
        const val TAG = "EngineManager"
        const val MODULE_NAME = "hermes_agent"
        const val ENGINE_PORT = 5000
    }

    data class EngineState(
        val pythonReady: Boolean = false,
        val engineRunning: Boolean = false,
        val tools: List<String> = emptyList(),
        val skillsCount: Int = 0,
        val pythonVersion: String? = null,
        val error: String? = null,
    )

    private var currentState = EngineState()

    /**
     * Initialize Chaquopy and load the Python engine.
     */
    suspend fun initialize(): EngineState =
        withContext(Dispatchers.IO) {
            try {
                // Step 1: Start Chaquopy Python runtime
                if (!Python.isStarted()) {
                    Python.start(AndroidPlatform(context))
                }
                val py = Python.getInstance()

                // Step 2: Load the hermes_agent module
                val module = py.getModule(MODULE_NAME)

                // Step 2b: Start the WebSocket gateway (port 9119) so the app
                // can connect to ws://127.0.0.1:9119/api/ws — the same JSON-RPC
                // protocol the desktop Hermes gateway speaks.
                try {
                    val gateway = py.getModule("hermes_gateway")
                    gateway.callAttr("start_gateway_background")
                    Log.d(TAG, "Gateway started on port 9119")
                } catch (ge: Exception) {
                    Log.w(TAG, "Gateway start failed (non-fatal): ${ge.message}")
                }

                // Step 3: Check engine status (tools, skills, python version).
                // get_status_json() returns a JSON string — Chaquopy's PyObject
                // nested-list conversion is unreliable ("Python null, 1 tools"),
                // so we parse JSON which is always reliable.
                val statusJson = module.callAttr("get_status_json").toString()
                val status = org.json.JSONObject(statusJson)

                val toolsArr = status.optJSONArray("tools") ?: JSONArray()
                val toolsList = mutableListOf<String>()
                for (i in 0 until toolsArr.length()) {
                    toolsArr.optString(i).takeIf { it.isNotEmpty() }?.let(toolsList::add)
                }
                val skillsCount = status.optInt("skills", 0)
                val pyVersion = status.optString("python", "")

                currentState =
                    currentState.copy(
                        pythonReady = true,
                        engineRunning = true,
                        tools = toolsList,
                        skillsCount = skillsCount,
                        pythonVersion = pyVersion,
                    )
                Log.d(TAG, "Engine ready: Python $pyVersion, ${currentState.tools.size} tools, $skillsCount skills")
                currentState
            } catch (e: Exception) {
                Log.e(TAG, "Engine initialization failed", e)
                currentState = currentState.copy(error = e.message)
                currentState
            }
        }

    /**
     * Send a chat message to the Python engine and get the reply.
     */
    suspend fun chat(message: String): String =
        withContext(Dispatchers.IO) {
            try {
                ensureEngine()
                val py = Python.getInstance()
                val module = py.getModule(MODULE_NAME)
                val result = module.callAttr("process_chat", message)
                result.get("response").toString()
            } catch (e: Exception) {
                Log.e(TAG, "Chat failed", e)
                "Engine error: ${e.message}"
            }
        }

    /**
     * Run a tool by name with args/kwargs.
     */
    suspend fun runTool(
        name: String,
        args: List<Any> = emptyList(),
        kwargs: Map<String, Any> = emptyMap(),
    ): String =
        withContext(Dispatchers.IO) {
            try {
                ensureEngine()
                val py = Python.getInstance()
                val module = py.getModule(MODULE_NAME)
                val result = module.callAttr("run_tool", name, args, kwargs)
                result.get("result").toString()
            } catch (e: Exception) {
                Log.e(TAG, "Tool $name failed", e)
                "Tool error: ${e.message}"
            }
        }

    /**
     * Get the current engine status (for UI display).
     */
    suspend fun getStatus(): EngineState =
        withContext(Dispatchers.IO) {
            if (!currentState.engineRunning) {
                initialize()
            }
            currentState
        }

    /**
     * Shut down the engine and reset state.
     * Called by [HermesEngineService.stopEngine] when the foreground service stops.
     */
    fun shutdown() {
        Log.d(TAG, "Engine shutdown requested")
        currentState = EngineState()
    }

    private fun ensureEngine() {
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(context))
        }
    }
}
