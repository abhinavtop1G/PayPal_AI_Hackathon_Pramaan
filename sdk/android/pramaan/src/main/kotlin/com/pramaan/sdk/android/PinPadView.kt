package com.pramaan.sdk.android

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.view.MotionEvent
import android.widget.Button
import android.widget.GridLayout
import com.pramaan.sdk.core.KeystrokeRecorder

/**
 * An in-app PIN / password pad that records typing rhythm. System keyboards do not tell apps when keys go down and
 * up, so banks that want typing biometrics use their own pad (most already do for the MPIN / UPI PIN). Each key's
 * press and release time goes to the [KeystrokeRecorder]; the digits stay in this view and are never recorded.
 *
 *   val pad = Pramaan.get().pinPad(this, maxLength = 10) { pin -> submit(pin) }
 */
@SuppressLint("ViewConstructor", "ClickableViewAccessibility")
class PinPadView(
    context: Context,
    private val recorder: KeystrokeRecorder,
    var maxLength: Int = 6,
    var onChange: ((length: Int) -> Unit)? = null,
    var onSubmit: ((pin: String) -> Unit)? = null,
    private val lock: Any = Any(),
) : GridLayout(context) {
    private val digits = StringBuilder()

    val length: Int get() = digits.length

    init {
        columnCount = 3
        val keys = listOf("1", "2", "3", "4", "5", "6", "7", "8", "9", "⌫", "0", "✓")
        keys.forEach { label -> addView(key(label)) }
    }

    fun clear() {
        digits.setLength(0)
        recorder.blur()
        onChange?.invoke(0)
    }

    private fun key(label: String): Button {
        val code = when (label) {
            "⌫" -> "Backspace"
            "✓" -> "Enter"
            else -> "Digit$label"
        }
        val dp = resources.displayMetrics.density
        return Button(context).apply {
            text = label
            textSize = 22f
            typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
            setTextColor(Color.WHITE)
            isAllCaps = false
            background = GradientDrawable().apply {
                shape = GradientDrawable.OVAL
                setColor(if (code == "Enter") Color.rgb(10, 132, 255) else Color.argb(46, 120, 120, 128))
            }
            layoutParams = LayoutParams(spec(UNDEFINED, 1f), spec(UNDEFINED, 1f)).apply {
                width = (72 * dp).toInt()
                height = (72 * dp).toInt()
                setMargins((10 * dp).toInt(), (8 * dp).toInt(), (10 * dp).toInt(), (8 * dp).toInt())
            }
            contentDescription = when (code) {
                "Backspace" -> "Delete"
                "Enter" -> "Submit"
                else -> label
            }
            setOnTouchListener { _, ev ->
                when (ev.actionMasked) {
                    MotionEvent.ACTION_DOWN -> synchronized(lock) { recorder.down(code, ev.eventTime.toDouble()) }
                    MotionEvent.ACTION_UP -> {
                        // the time goes to the recorder first, so Enter finishes the attempt before submit runs
                        synchronized(lock) { recorder.up(code, ev.eventTime.toDouble()) }
                        press(code, label)
                    }
                    MotionEvent.ACTION_CANCEL -> synchronized(lock) { recorder.blur() }
                }
                false
            }
        }
    }

    private fun press(code: String, label: String) {
        when (code) {
            "Backspace" -> if (digits.isNotEmpty()) digits.setLength(digits.length - 1)
            "Enter" -> {
                onSubmit?.invoke(digits.toString())
                digits.setLength(0)
            }
            else -> if (digits.length < maxLength) digits.append(label)
        }
        onChange?.invoke(digits.length)
    }
}
