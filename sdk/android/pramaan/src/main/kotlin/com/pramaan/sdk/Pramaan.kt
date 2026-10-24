package com.pramaan.sdk

import android.app.Activity
import android.app.Application
import android.content.Context
import android.os.Bundle
import android.os.SystemClock
import android.view.KeyEvent
import android.view.View
import com.pramaan.sdk.android.CallMonitor
import com.pramaan.sdk.android.DeviceSignals
import com.pramaan.sdk.android.MotionCapture
import com.pramaan.sdk.android.PinPadView
import com.pramaan.sdk.android.ScreenRecordingWatch
import com.pramaan.sdk.android.TouchCallback
import com.pramaan.sdk.core.AuthBehaviour
import com.pramaan.sdk.core.AuthDevice
import com.pramaan.sdk.core.AuthNetwork
import com.pramaan.sdk.core.AuthRequest
import com.pramaan.sdk.core.AuthTransaction
import com.pramaan.sdk.core.KeystrokeAttempt
import com.pramaan.sdk.core.KeystrokeRecorder
import com.pramaan.sdk.core.KeystrokeSpec
import com.pramaan.sdk.core.ScreenSize
import com.pramaan.sdk.core.TouchTracker
import com.pramaan.sdk.net.Fallback
import com.pramaan.sdk.net.PramaanClient
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import kotlin.math.min

data class PramaanConfig(
    /** PRAMAAN's URL, for open demo paths only. In production send collect()'s request to your backend instead. */
    val baseUrl: String? = null,
    /** The customer agreed to behavioural biometrics (DPDP purpose `behavioural_biometrics`); without it no touch,
     *  motion or typing data is collected. Device and session signals still are. */
    val consent: Boolean = true,
    val touch: Boolean = true,
    val motion: Boolean = true,
    /** watch every activity automatically (otherwise call attach / detach yourself) */
    val autoAttach: Boolean = true,
    val keepGestures: Int = 20,
    /** a call whose caller cannot be checked against contacts counts as an unknown call */
    val unverifiedCallIsUnknown: Boolean = true,
    /** hours since the SIM changed from a telecom SIM-swap API; null = use what this install observed */
    val simChangeHours: (() -> Double?)? = null,
    val timeoutMs: Int = 3000,
    val fallback: Fallback = Fallback.CHALLENGE,
)

/**
 * The Android SDK. Watches the app and builds the request PRAMAAN scores:
 *   behaviour  touch gestures (21 features each, with 100 Hz hand motion), one PIN / password attempt's rhythm,
 *              time to submit, input count, an unknown caller on the line
 *   device     install ID, root, emulator, remote-control apps, screen recording, SIM change
 *
 *   class App : Application() { override fun onCreate() { super.onCreate(); Pramaan.init(this) } }
 *   // payment screen
 *   Pramaan.get().startFlow()
 *   val req = Pramaan.get().collect(userId, transaction = AuthTransaction(amount = 2500.0, payeeId = "kirana-sharma"))
 *   // → your backend → POST /v1/authenticate
 */
class Pramaan private constructor(private val app: Application, val config: PramaanConfig) : Application.ActivityLifecycleCallbacks {
    private val lock = Any()
    val touch = TouchTracker(ScreenSize(1080.0, 1920.0), config.keepGestures)
    val typing = KeystrokeRecorder()
    private val motion = MotionCapture(app, touch, lock)
    private val calls = CallMonitor(app, config.unverifiedCallIsUnknown)
    private val recording = ScreenRecordingWatch()
    private var consent = config.consent
    private var flowStart: Long? = null
    @Volatile
    private var inputs = 0

    /** Client for open demo paths, when [PramaanConfig.baseUrl] is set. */
    val client: PramaanClient? by lazy {
        config.baseUrl?.let { PramaanClient(it, timeoutMs = config.timeoutMs, fallback = config.fallback) }
    }

    init {
        if (config.autoAttach) app.registerActivityLifecycleCallbacks(this)
    }

    /** Start observing an activity's touches (done for you with autoAttach). */
    fun attach(activity: Activity) {
        val w = activity.window ?: return
        if (w.callback is TouchCallback) return
        w.callback = TouchCallback(w.callback, activity, touch, lock, { consent && config.touch }, { inputs++ })
    }

    fun detach(activity: Activity) {
        val w = activity.window ?: return
        (w.callback as? TouchCallback)?.let { w.callback = it.base }
    }

    /** The payment / login screen opened: starts the time-to-submit clock and the input count. */
    fun startFlow() {
        flowStart = SystemClock.uptimeMillis()
        inputs = 0
    }

    fun setConsent(granted: Boolean) {
        consent = granted
        if (!granted) synchronized(lock) {
            touch.reset()
            typing.reset()
        }
    }

    /** A PIN / password pad that records typing rhythm (system keyboards do not expose key timing). */
    fun pinPad(context: Context, maxLength: Int = 6, onSubmit: (String) -> Unit): PinPadView =
        PinPadView(context, typing, maxLength, onSubmit = onSubmit, lock = lock)

    /** Typing rhythm from a hardware keyboard: set as the field's OnKeyListener. */
    fun keyListener(): View.OnKeyListener = View.OnKeyListener { _, keyCode, event ->
        if (consent) {
            val code = keyName(keyCode)
            synchronized(lock) {
                when (event.action) {
                    KeyEvent.ACTION_DOWN -> typing.down(code, event.eventTime.toDouble(), event.repeatCount > 0)
                    KeyEvent.ACTION_UP -> typing.up(code, event.eventTime.toDouble())
                }
            }
        }
        false
    }

    /** What this phone says about itself right now. */
    fun device(): AuthDevice {
        val controlling = DeviceSignals.remoteAccessControlling(app)
        val capturing = recording.recording || DeviceSignals.castDisplayConnected(app)
        return AuthDevice(
            deviceId = DeviceSignals.deviceId(app),
            platform = "android",
            isEmulator = DeviceSignals.isEmulator(),
            isRooted = DeviceSignals.isRooted(app),
            remoteAccessApp = controlling.isNotEmpty() || (capturing && DeviceSignals.remoteAccessInstalled(app).isNotEmpty()),
            screenShareActive = capturing,
            simChangeHours = config.simChangeHours?.invoke() ?: DeviceSignals.simChangeHours(app),
        )
    }

    /** Build the request for /v1/authenticate. Call it from any thread; device checks take a few ms. */
    fun collect(
        userId: String,
        eventType: String = "payment",
        transaction: AuthTransaction = AuthTransaction(),
        network: AuthNetwork = AuthNetwork(),
        requestId: String? = null,
    ): AuthRequest {
        val (gestures, attempt) = synchronized(lock) {
            touch.settle(SystemClock.uptimeMillis().toDouble(), force = true)
            val g = if (consent && touch.count >= 10) touch.window(min(20, touch.count)) else null
            val a: KeystrokeAttempt? = if (consent) typing.lastAttempt ?: typing.current() else null
            g to a
        }
        val start = flowStart
        return AuthRequest(
            userId = userId,
            device = device(),
            channel = "mobile",
            eventType = eventType,
            network = network,
            behaviour = AuthBehaviour(
                gestures = gestures,
                keystrokes = attempt?.takeIf { it.keys == KeystrokeSpec.KEYS }?.timings,
                timeToSubmitS = start?.let { (SystemClock.uptimeMillis() - it) / 1000.0 },
                inputEvents = start?.let { inputs },
                unknownCallActive = calls.unknownCallActive(),
            ),
            transaction = transaction,
            requestId = requestId,
            ts = ISO.get()!!.format(Date()),
        )
    }

    // ------------------------------------------------------------------ lifecycle
    override fun onActivityCreated(a: Activity, b: Bundle?) = attach(a)
    override fun onActivityStarted(a: Activity) = Unit
    override fun onActivityResumed(a: Activity) {
        attach(a)
        if (config.motion && consent) motion.start()
        recording.start(a)
    }
    override fun onActivityPaused(a: Activity) {
        motion.stop()
        recording.stop()
    }
    override fun onActivityStopped(a: Activity) = Unit
    override fun onActivitySaveInstanceState(a: Activity, b: Bundle) = Unit
    override fun onActivityDestroyed(a: Activity) = detach(a)

    companion object {
        @Volatile
        private var instance: Pramaan? = null

        @JvmStatic
        @JvmOverloads
        fun init(context: Context, config: PramaanConfig = PramaanConfig()): Pramaan = synchronized(this) {
            instance ?: Pramaan(context.applicationContext as Application, config).also { instance = it }
        }

        @JvmStatic
        fun get(): Pramaan = instance ?: error("call Pramaan.init(context) in Application.onCreate first")

        private val ISO = object : ThreadLocal<SimpleDateFormat>() {
            override fun initialValue() = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss.SSSXXX", Locale.US).apply {
                timeZone = TimeZone.getTimeZone("UTC")
            }
        }

        private fun keyName(keyCode: Int): String = when (keyCode) {
            KeyEvent.KEYCODE_ENTER, KeyEvent.KEYCODE_NUMPAD_ENTER -> "Enter"
            KeyEvent.KEYCODE_DEL -> "Backspace"
            KeyEvent.KEYCODE_FORWARD_DEL -> "Delete"
            KeyEvent.KEYCODE_SHIFT_LEFT -> "ShiftLeft"
            KeyEvent.KEYCODE_SHIFT_RIGHT -> "ShiftRight"
            KeyEvent.KEYCODE_CTRL_LEFT -> "ControlLeft"
            KeyEvent.KEYCODE_CTRL_RIGHT -> "ControlRight"
            KeyEvent.KEYCODE_ALT_LEFT -> "AltLeft"
            KeyEvent.KEYCODE_ALT_RIGHT -> "AltRight"
            KeyEvent.KEYCODE_CAPS_LOCK -> "CapsLock"
            KeyEvent.KEYCODE_TAB -> "Tab"
            else -> KeyEvent.keyCodeToString(keyCode)
        }
    }
}
