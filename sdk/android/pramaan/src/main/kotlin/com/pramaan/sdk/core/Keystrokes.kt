package com.pramaan.sdk.core

import kotlin.math.roundToLong

/**
 * Typing rhythm of one password / PIN attempt, in the layout the keystroke model was trained on
 * (ml/models/keystroke/data.py COLUMNS): for each pair of consecutive keys a→b the hold of a, the down-down latency
 * and the up-down latency (negative when b goes down before a comes up), then the hold of the last key. 11 keys
 * (10 characters + Enter, as in the CMU benchmark) give the 31 timings the service scores.
 *
 * Only timings are kept; which keys were pressed is never recorded.
 */
object KeystrokeSpec {
    const val KEYS = 11
    const val TIMINGS = 31

    data class KeyTiming(val down: Double, val up: Double)

    /** 3·(n−1)+1 timings in seconds for n keys (times in ms), in model order. */
    fun timings(keys: List<KeyTiming>): List<Double> {
        val out = ArrayList<Double>(3 * keys.size)
        for (i in 0 until keys.size - 1) {
            val a = keys[i]
            val b = keys[i + 1]
            out += (a.up - a.down) / 1000
            out += (b.down - a.down) / 1000
            out += (b.down - a.up) / 1000
        }
        keys.lastOrNull()?.let { out += (it.up - it.down) / 1000 }
        return out.map { (it * 1e6).roundToLong() / 1e6 }
    }
}

data class KeystrokeAttempt(val keys: Int, val timings: List<Double>, val submitted: Boolean)

/**
 * Records key-down / key-up times for one attempt, from a hardware keyboard (KeyEvent) or the SDK's [PinPadView]
 * (soft keyboards do not report key timing to apps). A correction, paste or leaving the field restarts the attempt;
 * auto-repeat and modifier keys are ignored; keys are matched by code, so rollover is handled. "Enter" ends it.
 */
class KeystrokeRecorder(
    private val onAttempt: ((KeystrokeAttempt) -> Unit)? = null,
    private val onReset: ((String) -> Unit)? = null,
) {
    private class Key(val code: String, val down: Double, var up: Double? = null)

    private val keys = mutableListOf<Key>()
    var lastAttempt: KeystrokeAttempt? = null
        private set

    fun down(code: String, t: Double, repeat: Boolean = false) {
        if (repeat || code in MODIFIERS) return
        if (code in EDIT) return restart("edit")
        if (code in NAV) return restart("navigation")
        if (keys.any { it.code == code && it.up == null }) return
        keys += Key(code, t)
    }

    fun up(code: String, t: Double) {
        if (code in MODIFIERS) return
        keys.lastOrNull { it.code == code && it.up == null }?.up = t
        if (code in SUBMIT) finish()
    }

    fun paste() = restart("paste")

    fun blur() {
        if (keys.isNotEmpty()) restart("blur")
    }

    /** The attempt so far without Enter (a button submitted instead). */
    fun current(): KeystrokeAttempt? {
        if (keys.isEmpty() || keys.any { it.up == null }) return null
        return KeystrokeAttempt(keys.size, KeystrokeSpec.timings(keys.map { KeystrokeSpec.KeyTiming(it.down, it.up!!) }), false)
    }

    fun reset() {
        keys.clear()
        lastAttempt = null
    }

    private fun finish() {
        if (keys.isNotEmpty() && keys.all { it.up != null }) {
            val a = KeystrokeAttempt(keys.size, KeystrokeSpec.timings(keys.map { KeystrokeSpec.KeyTiming(it.down, it.up!!) }), true)
            lastAttempt = a
            onAttempt?.invoke(a)
        }
        keys.clear()
    }

    private fun restart(why: String) {
        keys.clear()
        onReset?.invoke(why)
    }

    companion object {
        val MODIFIERS = setOf("ShiftLeft", "ShiftRight", "ControlLeft", "ControlRight", "AltLeft", "AltRight",
            "MetaLeft", "MetaRight", "CapsLock", "Fn", "FnLock", "NumLock")
        val SUBMIT = setOf("Enter", "NumpadEnter")
        val EDIT = setOf("Backspace", "Delete")
        val NAV = setOf("ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End", "Tab", "Escape")
    }
}
