package com.pramaan.sample

import android.app.Activity
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import com.pramaan.sdk.Pramaan
import com.pramaan.sdk.core.AuthResponse
import com.pramaan.sdk.core.AuthTransaction
import com.pramaan.sdk.core.Decision

/**
 * A UPI-style payment screen wired to the SDK: touches anywhere on the screen are gestures, the passcode pad records
 * typing rhythm, and "Pay" sends the collected request for a decision. A challenge can be passed or failed to see
 * the final decision. Built in code to keep the sample to two files.
 */
class PaymentActivity : Activity() {
    private val pramaan by lazy { Pramaan.get() }
    private var amount = 640.0
    private lateinit var status: TextView
    private lateinit var result: LinearLayout
    private lateinit var dots: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val dp = resources.displayMetrics.density
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.BLACK)
            setPadding((20 * dp).toInt(), (28 * dp).toInt(), (20 * dp).toInt(), (20 * dp).toInt())
        }
        root.addView(text("Pay Sharma Kirana", 24f, bold = true))
        root.addView(text("kirana-sharma@upi · merchant", 14f, color = GRAY))

        val amounts = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, (16 * dp).toInt(), 0, 0) }
        listOf(640.0, 18_500.0, 60_000.0).forEach { a ->
            amounts.addView(chip("₹%,.0f".format(a)) {
                amount = a
                refresh()
            })
        }
        root.addView(amounts)

        root.addView(text("Enter a 10-digit passcode, then ✓", 14f, color = GRAY).apply { setPadding(0, (20 * dp).toInt(), 0, 0) })
        dots = text("", 26f, bold = true).apply { gravity = Gravity.CENTER; letterSpacing = 0.3f }
        root.addView(dots)
        val pad = pramaan.pinPad(this, maxLength = 10) { pay() }
        pad.onChange = { n -> dots.text = "●".repeat(n) + "○".repeat(10 - n) }
        pad.onChange?.invoke(0)
        root.addView(pad, LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, LinearLayout.LayoutParams.WRAP_CONTENT)
            .apply { gravity = Gravity.CENTER_HORIZONTAL })

        status = text("", 13f, color = GRAY).apply { typeface = Typeface.MONOSPACE }
        root.addView(status)
        result = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        root.addView(result)

        setContentView(ScrollView(this).apply { addView(root) })
        pramaan.startFlow()
        refresh()
    }

    private fun refresh() {
        val d = pramaan.device()
        status.text = "amount ₹%,.0f · gestures %d · typing %s\ndevice %s · rooted %b · emulator %b · remote %b · SIM Δ %s h".format(
            amount, pramaan.touch.count, pramaan.typing.lastAttempt?.let { "${it.keys} keys" } ?: "—",
            d.deviceId.take(16), d.isRooted, d.isEmulator, d.remoteAccessApp, d.simChangeHours?.let { "%.0f".format(it) } ?: "—")
    }

    private fun pay() {
        val req = pramaan.collect("demo-asha", transaction = AuthTransaction(amount = amount, payeeId = "kirana-sharma", payeeIsMerchant = true))
        refresh()
        show("Deciding…", GRAY)
        pramaan.client!!.authenticateAsync(req) { r ->
            runOnUiThread {
                r.onSuccess(::render).onFailure { show("Error: ${it.message}", RED) }
                pramaan.startFlow()
            }
        }
    }

    private fun render(r: AuthResponse) {
        val tint = when (r.decision) { Decision.ALLOW -> GREEN; Decision.CHALLENGE -> ORANGE; Decision.BLOCK -> RED }
        show("${r.decision.name.lowercase().replaceFirstChar { it.uppercase() }}${r.challengeType?.let { " · $it" } ?: ""}" +
            "   risk %.2f%% · %.0f ms".format(100 * r.riskScore, r.latencyMs), tint)
        result.addView(text(r.messageEn, 15f))
        result.addView(text(r.messageHi, 15f, color = GRAY))
        r.reasons.forEach { (en, _) -> result.addView(text("• $en", 14f)) }
        if (r.decision == Decision.CHALLENGE) {
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            row.addView(chip("Challenge passed") { verify(r, true) })
            row.addView(chip("Failed") { verify(r, false) })
            result.addView(row)
        }
    }

    private fun verify(r: AuthResponse, passed: Boolean) {
        pramaan.client!!.verifyChallengeAsync(r.decisionId, passed) { out ->
            runOnUiThread {
                out.onSuccess { o ->
                    show("Final: ${o.decision.name.lowercase()}${if (o.deviceTrusted) " · device now trusted" else ""}",
                        if (o.decision == Decision.ALLOW) GREEN else RED)
                    result.addView(text(o.messageEn, 15f))
                }.onFailure { show("Error: ${it.message}", RED) }
            }
        }
    }

    private fun show(headline: String, tint: Int) {
        result.removeAllViews()
        result.addView(text(headline, 18f, bold = true, color = tint).apply { setPadding(0, (16 * resources.displayMetrics.density).toInt(), 0, 0) })
    }

    private fun text(s: String, size: Float, bold: Boolean = false, color: Int = Color.WHITE) = TextView(this).apply {
        text = s
        textSize = size
        setTextColor(color)
        if (bold) typeface = Typeface.DEFAULT_BOLD
    }

    private fun chip(label: String, onClick: () -> Unit) = Button(this).apply {
        text = label
        isAllCaps = false
        setTextColor(Color.WHITE)
        background = GradientDrawable().apply {
            cornerRadius = 999f
            setColor(Color.argb(60, 120, 120, 128))
        }
        val dp = resources.displayMetrics.density
        layoutParams = LinearLayout.LayoutParams(LinearLayout.LayoutParams.WRAP_CONTENT, (40 * dp).toInt()).apply {
            setMargins(0, 0, (8 * dp).toInt(), 0)
        }
        setPadding((16 * dp).toInt(), 0, (16 * dp).toInt(), 0)
        setOnClickListener { onClick() }
        visibility = View.VISIBLE
    }

    private companion object {
        val GRAY = Color.rgb(142, 142, 147)
        val GREEN = Color.rgb(48, 209, 88)
        val ORANGE = Color.rgb(255, 159, 10)
        val RED = Color.rgb(255, 69, 58)
    }
}
