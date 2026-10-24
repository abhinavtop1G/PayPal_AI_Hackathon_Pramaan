package com.pramaan.sdk.android

import android.app.Activity
import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.MotionEvent
import android.view.Surface
import android.view.Window
import android.view.WindowManager
import com.pramaan.sdk.core.ScreenSize
import com.pramaan.sdk.core.TouchPoint
import com.pramaan.sdk.core.TouchTracker
import java.util.concurrent.Executor
import java.util.function.Consumer

/**
 * Sees every touch on an activity without changing how the app handles it: wraps the window's callback and forwards
 * each event unchanged. Only the event's own position is used, not its batched history, because the training data
 * (HMOG) logged one point per touch event.
 */
internal class TouchCallback(
    val base: Window.Callback,
    private val activity: Activity,
    private val tracker: TouchTracker,
    private val lock: Any,
    private val enabled: () -> Boolean,
    private val onInput: () -> Unit,
) : Window.Callback by base {
    override fun dispatchTouchEvent(event: MotionEvent?): Boolean {
        if (event != null) {
            if (event.actionMasked == MotionEvent.ACTION_DOWN) onInput()
            if (enabled()) synchronized(lock) { capture(event) }
        }
        return base.dispatchTouchEvent(event)
    }

    private fun capture(ev: MotionEvent) {
        val t = ev.eventTime.toDouble()
        val point = { i: Int -> TouchPoint(t, ev.getRawXCompat(i), ev.getRawYCompat(i), ev.getSize(i).toDouble()) }
        when (ev.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                tracker.screen = screenSize(activity)
                tracker.rotated = rotation(activity) != Surface.ROTATION_0
                tracker.down(ev.getPointerId(0), point(0))
            }
            MotionEvent.ACTION_POINTER_DOWN -> tracker.down(ev.getPointerId(ev.actionIndex), point(ev.actionIndex))
            MotionEvent.ACTION_MOVE -> tracker.move(ev.getPointerId(0), point(0))
            MotionEvent.ACTION_UP -> tracker.up(ev.getPointerId(0), point(0))
            MotionEvent.ACTION_CANCEL -> tracker.cancel()
        }
    }

    private fun MotionEvent.getRawXCompat(i: Int): Double =
        if (Build.VERSION.SDK_INT >= 29) getRawX(i).toDouble() else (getX(i) + rawX - x).toDouble()

    private fun MotionEvent.getRawYCompat(i: Int): Double =
        if (Build.VERSION.SDK_INT >= 29) getRawY(i).toDouble() else (getY(i) + rawY - y).toDouble()

    companion object {
        fun screenSize(a: Activity): ScreenSize {
            val m = a.resources.displayMetrics
            return ScreenSize(m.widthPixels.toDouble().coerceAtLeast(1.0), m.heightPixels.toDouble().coerceAtLeast(1.0))
        }

        @Suppress("DEPRECATION")
        fun rotation(a: Activity): Int =
            if (Build.VERSION.SDK_INT >= 30) a.display?.rotation ?: Surface.ROTATION_0 else a.windowManager.defaultDisplay.rotation
    }
}

/**
 * Accelerometer (m/s², with gravity) and gyroscope (rad/s) at 100 Hz while an activity is in the foreground, on the
 * main looper so samples and touches arrive on one thread. Sensor timestamps (since boot) are moved onto the touch
 * clock (uptime).
 */
internal class MotionCapture(ctx: Context, private val tracker: TouchTracker, private val lock: Any) : SensorEventListener {
    private val sm = ctx.getSystemService(Context.SENSOR_SERVICE) as? SensorManager
    private val handler = Handler(Looper.getMainLooper())
    private var running = false

    val available: Boolean get() = sm?.getDefaultSensor(Sensor.TYPE_ACCELEROMETER) != null

    fun start() {
        if (running || sm == null) return
        running = true
        sm.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)?.let { sm.registerListener(this, it, PERIOD_US, handler) }
        sm.getDefaultSensor(Sensor.TYPE_GYROSCOPE)?.let { sm.registerListener(this, it, PERIOD_US, handler) }
    }

    fun stop() {
        if (!running) return
        running = false
        sm?.unregisterListener(this)
    }

    override fun onSensorChanged(e: SensorEvent) {
        val offsetNs = SystemClock.elapsedRealtimeNanos() - SystemClock.uptimeMillis() * 1_000_000
        val t = (e.timestamp - offsetNs) / 1e6
        val (x, y, z) = Triple(e.values[0].toDouble(), e.values[1].toDouble(), e.values[2].toDouble())
        synchronized(lock) {
            when (e.sensor.type) {
                Sensor.TYPE_ACCELEROMETER -> tracker.acc.push(t, x, y, z)
                Sensor.TYPE_GYROSCOPE -> tracker.gyr.push(t, x, y, z)
            }
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) = Unit

    private companion object {
        const val PERIOD_US = 10_000
    }
}

/**
 * Android 15+: is this activity's screen being recorded or shared right now (screen-share apps, remote-control
 * apps that capture the screen)? Needs android.permission.DETECT_SCREEN_RECORDING (declared by the SDK).
 */
internal class ScreenRecordingWatch {
    @Volatile
    var recording = false
        private set
    private var registered: Pair<WindowManager, Consumer<Int>>? = null

    fun start(a: Activity) {
        if (Build.VERSION.SDK_INT < 35 || registered != null) return
        val wm = a.windowManager
        val cb = Consumer<Int> { state -> recording = state == WindowManager.SCREEN_RECORDING_STATE_VISIBLE }
        runCatching {
            val initial = wm.addScreenRecordingCallback(Executor { it.run() }, cb)
            recording = initial == WindowManager.SCREEN_RECORDING_STATE_VISIBLE
            registered = wm to cb
        }
    }

    fun stop() {
        val r = registered ?: return
        if (Build.VERSION.SDK_INT >= 35) runCatching { r.first.removeScreenRecordingCallback(r.second) }
        registered = null
        recording = false
    }
}
