package com.m57.hermescontrol.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import com.m57.hermescontrol.MainActivity
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * Foreground service that manages the Hermes Engine lifecycle.
 * Starts libtermux (Linux env), Node.js (LocalBridge), and Python (Agent Engine).
 */
class HermesEngineService : Service() {
    companion object {
        const val TAG = "HermesEngine"
        const val CHANNEL_ID = "hermes_engine_channel"
        const val NOTIFICATION_ID = 1001
        const val ACTION_START = "com.m57.hermescontrol.action.START_ENGINE"
        const val ACTION_STOP = "com.m57.hermescontrol.action.STOP_ENGINE"

        private val _engineStatus = MutableStateFlow(EngineStatus.STOPPED)
        val engineStatus: StateFlow<EngineStatus> = _engineStatus
    }

    private val serviceScope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var engineManager: EngineManager? = null

    enum class EngineStatus {
        STOPPED,
        INITIALIZING,
        INSTALLING_PACKAGES,
        STARTING_LOCALBRIDGE,
        STARTING_PYTHON,
        READY,
        ERROR,
    }

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
    }

    override fun onStartCommand(
        intent: Intent?,
        flags: Int,
        startId: Int,
    ): Int {
        when (intent?.action) {
            ACTION_START -> {
                startForeground(NOTIFICATION_ID, createNotification("Starting Hermes Engine..."))
                _engineStatus.value = EngineStatus.INITIALIZING
                startEngine()
            }
            ACTION_STOP -> {
                stopEngine()
                stopSelf()
            }
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        stopEngine()
        serviceScope.cancel()
        super.onDestroy()
    }

    private fun startEngine() {
        serviceScope.launch {
            try {
                engineManager = EngineManager(this@HermesEngineService)
                engineManager?.initialize()
                _engineStatus.value = EngineStatus.READY
                updateNotification("Hermes Engine Ready ✅")
            } catch (e: Exception) {
                Log.e(TAG, "Engine failed to start", e)
                _engineStatus.value = EngineStatus.ERROR
                updateNotification("Engine Error: ${e.message}")
            }
        }
    }

    private fun stopEngine() {
        engineManager?.shutdown()
        engineManager = null
        _engineStatus.value = EngineStatus.STOPPED
    }

    private fun createNotificationChannel() {
        val channel =
            NotificationChannel(
                CHANNEL_ID,
                "Hermes Engine",
                NotificationManager.IMPORTANCE_LOW,
            ).apply {
                description = "Hermes AI Engine background service"
            }
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(channel)
    }

    private fun createNotification(text: String): Notification {
        val pendingIntent =
            PendingIntent.getActivity(
                this,
                0,
                Intent(this, MainActivity::class.java),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
            )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Hermes Engine")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_menu_compass)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .build()
    }

    private fun updateNotification(text: String) {
        val manager = getSystemService(NotificationManager::class.java)
        manager.notify(NOTIFICATION_ID, createNotification(text))
    }
}
