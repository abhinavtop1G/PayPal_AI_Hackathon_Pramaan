package com.pramaan.sdk.core

import kotlin.math.hypot
import kotlin.math.ln1p
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sqrt

/**
 * Touch-gesture features, computed on the phone exactly as the touch-biometrics model was trained
 * (ml/models/biometrics/data.py: extract_gestures + add_motion_features). Only these 21 numbers per gesture leave the
 * device; raw coordinates and sensor streams stay on it. Checked against sdk/spec/golden.json.
 */
object GestureSpec {
    val FEATURES = listOf(
        "log_duration_ms", "log_gap_ms", "size_mean", "size_max",
        "dx", "dy", "log_path_len", "log_speed", "log_n_points", "x0", "y0", "is_tap",
        "acc_mean", "acc_std", "acc_pre", "acc_resist", "gyr_mean", "gyr_std", "gyr_pre", "gyr_resist", "rotated",
    )

    /** Width of the HMOG phone the model was trained on; path lengths are rescaled to it. */
    const val REFERENCE_WIDTH_PX = 1080.0
    const val TAP_MAX_PATH_PX = 20.0
    const val MAX_DURATION_MS = 5000.0
    const val MAX_GAP_MS = 60_000.0
    const val SENSOR_PRE_MS = 100.0
    const val SENSOR_POST_MS = 100.0
}

/** ms on a monotonic clock shared with the motion samples; x, y in screen pixels; size = MotionEvent.getSize(). */
data class TouchPoint(val t: Double, val x: Double, val y: Double, val size: Double? = null)

class Gesture(
    val points: MutableList<TouchPoint> = mutableListOf(),
    var rotated: Boolean = false,
    var multiTouch: Boolean = false,
    var ended: Boolean = false,
)

data class ScreenSize(val width: Double, val height: Double)

/** One gesture as the model sees it: feature name -> value, null = not measured on this device. */
typealias GestureFeatures = Map<String, Double?>

/**
 * Turns finished gestures into features. Keeps the time the previous kept gesture lifted (`log_gap_ms` is the pause
 * before each gesture); gestures the training pipeline drops (multi-touch, never lifted, held >= 5 s) return null and
 * do not count as the previous gesture.
 */
class GestureEncoder(var screen: ScreenSize) {
    private var lastUp: Double? = null

    fun reset() {
        lastUp = null
    }

    fun encode(g: Gesture, acc: MotionBuffer? = null, gyr: MotionBuffer? = null): GestureFeatures? {
        val p = g.points
        if (p.isEmpty() || !g.ended || g.multiTouch) return null
        val first = p.first()
        val last = p.last()
        val dur = max(last.t - first.t, 1.0)
        if (dur >= GestureSpec.MAX_DURATION_MS) return null

        val gap = lastUp?.let { min(GestureSpec.MAX_GAP_MS, max(0.0, first.t - it)) } ?: GestureSpec.MAX_GAP_MS
        lastUp = last.t

        var path = 0.0
        var sizeSum = 0.0
        var sizeMax = Double.NEGATIVE_INFINITY
        var sized = 0
        for (i in p.indices) {
            if (i > 0) path += hypot(p[i].x - p[i - 1].x, p[i].y - p[i - 1].y)
            val s = p[i].size
            if (s != null && s.isFinite()) {
                sizeSum += s
                sizeMax = max(sizeMax, s)
                sized++
            }
        }
        path *= GestureSpec.REFERENCE_WIDTH_PX / screen.width
        val a = motion(acc, first.t, last.t)
        val r = motion(gyr, first.t, last.t)
        return linkedMapOf(
            "log_duration_ms" to ln1p(dur),
            "log_gap_ms" to ln1p(gap),
            "size_mean" to if (sized > 0) sizeSum / sized else null,
            "size_max" to if (sized > 0) sizeMax else null,
            "dx" to (last.x - first.x) / screen.width,
            "dy" to (last.y - first.y) / screen.height,
            "log_path_len" to ln1p(path),
            "log_speed" to ln1p(path / dur * 1000),
            "log_n_points" to ln1p(p.size.toDouble()),
            "x0" to first.x / screen.width,
            "y0" to first.y / screen.height,
            "is_tap" to if (path < GestureSpec.TAP_MAX_PATH_PX) 1.0 else 0.0,
            "acc_mean" to a[0], "acc_std" to a[1], "acc_pre" to a[2], "acc_resist" to a[3],
            "gyr_mean" to r[0], "gyr_std" to r[1], "gyr_pre" to r[2], "gyr_resist" to r[3],
            "rotated" to if (g.rotated) 1.0 else 0.0,
        )
    }

    private fun motion(s: MotionBuffer?, tDown: Double, tUp: Double): List<Double?> {
        if (s == null) return listOf(null, null, null, null)
        val (mean, std) = s.windowStats(tDown, tUp + GestureSpec.SENSOR_POST_MS)
        val (pre, _) = s.windowStats(tDown - GestureSpec.SENSOR_PRE_MS, tDown)
        return listOf(mean, std, pre, mean - pre).map { if (it.isFinite()) it else null }
    }
}

/**
 * A rolling window of sensor magnitudes (accelerometer |a| with gravity in m/s², or gyroscope |ω| in rad/s), kept just
 * long enough to give each touch its 100 ms of context before and after. Samples must arrive in time order.
 */
class MotionBuffer(private val keepMs: Double = 8000.0, capacity: Int = 2048) {
    private var t = DoubleArray(capacity)
    private var m = DoubleArray(capacity)
    var size = 0
        private set

    fun push(time: Double, x: Double, y: Double, z: Double) {
        if (size > 0 && time < t[size - 1]) return
        if (size == t.size) compact(time)
        if (size == t.size) {
            t = t.copyOf(t.size * 2)
            m = m.copyOf(m.size * 2)
        }
        t[size] = time
        m[size] = sqrt(x * x + y * y + z * z)
        size++
    }

    fun compact(now: Double) {
        var i = 0
        while (i < size && t[i] < now - keepMs) i++
        if (i == 0) return
        System.arraycopy(t, i, t, 0, size - i)
        System.arraycopy(m, i, m, 0, size - i)
        size -= i
    }

    fun clear() {
        size = 0
    }

    /** Mean and population std of the magnitudes in [lo, hi] (inclusive); NaN when too few samples. */
    fun windowStats(lo: Double, hi: Double): Pair<Double, Double> {
        val a = bound(lo, strict = false)
        val b = bound(hi, strict = true)
        val n = b - a
        if (n <= 0) return Double.NaN to Double.NaN
        var sum = 0.0
        var sq = 0.0
        for (i in a until b) {
            sum += m[i]
            sq += m[i] * m[i]
        }
        val mean = sum / n
        return mean to if (n > 1) sqrt(max(0.0, sq / n - mean * mean)) else Double.NaN
    }

    /** first index with t >= x (or t > x when strict) */
    private fun bound(x: Double, strict: Boolean): Int {
        var lo = 0
        var hi = size
        while (lo < hi) {
            val mid = (lo + hi) ushr 1
            if (t[mid] < x || (strict && t[mid] == x)) lo = mid + 1 else hi = mid
        }
        return lo
    }
}

/**
 * Platform-neutral touch state machine: feed it pointer down / move / up and it keeps the last N gestures as model
 * features. The first pointer is tracked; a second pointer landing during a gesture marks it multi-touch (dropped,
 * like the training data). Not thread-safe: feed touches and sensor samples from one thread (the main looper).
 */
class TouchTracker(screen: ScreenSize, private val keep: Int = 20, private val onGesture: ((GestureFeatures) -> Unit)? = null) {
    val acc = MotionBuffer()
    val gyr = MotionBuffer()
    private val encoder = GestureEncoder(screen)
    private var activeId: Int? = null
    private var active: Gesture? = null
    private val pending = ArrayDeque<Gesture>()
    private val kept = ArrayDeque<GestureFeatures>()
    var rotated = false

    var screen: ScreenSize
        get() = encoder.screen
        set(value) {
            encoder.screen = value
        }

    val count: Int get() = kept.size

    fun down(pointerId: Int, p: TouchPoint) {
        val g = active
        if (g != null) {
            if (pointerId != activeId) g.multiTouch = true
            return
        }
        activeId = pointerId
        active = Gesture(mutableListOf(p), rotated = rotated)
    }

    fun move(pointerId: Int, p: TouchPoint) {
        if (pointerId == activeId) active?.points?.add(p)
    }

    fun up(pointerId: Int, p: TouchPoint) {
        val g = active ?: return
        if (pointerId != activeId) return
        g.points.add(p)
        g.ended = true
        active = null
        activeId = null
        pending.addLast(g)
    }

    fun cancel() {
        active = null
        activeId = null
    }

    /** Encode lifted gestures whose 100 ms of motion context has arrived (or all of them with [force]). */
    fun settle(now: Double, force: Boolean = false) {
        while (pending.isNotEmpty()) {
            val g = pending.first()
            if (!force && g.points.last().t + GestureSpec.SENSOR_POST_MS > now) break
            pending.removeFirst()
            val f = encoder.encode(g, acc, gyr) ?: continue
            kept.addLast(f)
            if (kept.size > keep) kept.removeFirst()
            onGesture?.invoke(f)
        }
        acc.compact(now)
        gyr.compact(now)
    }

    /** The last [n] encoded gestures, oldest first. */
    fun window(n: Int = keep): List<GestureFeatures> = kept.toList().takeLast(n)

    fun reset() {
        cancel()
        pending.clear()
        kept.clear()
        encoder.reset()
        acc.clear()
        gyr.clear()
    }
}
