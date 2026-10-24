package com.pramaan.sdk.core

/**
 * The PRAMAAN request (backend/schemas.py AuthRequest) and responses. Requests are plain data classes that write their
 * wire JSON; responses keep the parsed JSON and expose typed fields, so new response fields never break old SDKs.
 */
data class AuthDevice(
    val deviceId: String,
    val platform: String = "android",
    val isEmulator: Boolean = false,
    val isRooted: Boolean = false,
    val remoteAccessApp: Boolean = false,
    val screenShareActive: Boolean = false,
    val simChangeHours: Double? = null,
) : JsonValue {
    override fun toJson() = linkedMapOf(
        "device_id" to deviceId, "platform" to platform, "is_emulator" to isEmulator, "is_rooted" to isRooted,
        "remote_access_app" to remoteAccessApp, "screen_share_active" to screenShareActive, "sim_change_hours" to simChangeHours,
    )
}

data class AuthNetwork(val ip: String? = null, val lat: Double? = null, val lon: Double? = null, val city: String? = null) : JsonValue {
    override fun toJson() = linkedMapOf<String, Any?>("ip" to ip, "lat" to lat, "lon" to lon, "city" to city)
}

data class AuthBehaviour(
    val gestures: List<GestureFeatures>? = null,
    val keystrokes: List<Double>? = null,
    val timeToSubmitS: Double? = null,
    val inputEvents: Int? = null,
    val unknownCallActive: Boolean = false,
) : JsonValue {
    override fun toJson() = linkedMapOf(
        "gestures" to gestures, "keystrokes" to keystrokes, "time_to_submit_s" to timeToSubmitS,
        "input_events" to inputEvents, "unknown_call_active" to unknownCallActive,
    )
}

data class AuthTransaction(
    val amount: Double = 0.0,
    val payeeId: String? = null,
    val payeeIsMerchant: Boolean? = null,
    val payeeRisk: Double? = null,
) : JsonValue {
    override fun toJson() = linkedMapOf<String, Any?>(
        "amount" to amount, "payee_id" to payeeId, "payee_is_merchant" to payeeIsMerchant, "payee_risk" to payeeRisk,
    )
}

data class AuthRequest(
    val userId: String,
    val device: AuthDevice,
    val channel: String = "mobile",
    val eventType: String = "payment",
    val network: AuthNetwork = AuthNetwork(),
    val behaviour: AuthBehaviour = AuthBehaviour(),
    val transaction: AuthTransaction = AuthTransaction(),
    val requestId: String? = null,
    /** ISO-8601; null = when the server receives it */
    val ts: String? = null,
) : JsonValue {
    override fun toJson(): Map<String, Any?> = linkedMapOf<String, Any?>(
        "user_id" to userId, "channel" to channel, "event_type" to eventType, "device" to device, "network" to network,
        "behaviour" to behaviour, "transaction" to transaction,
    ).apply {
        requestId?.let { put("request_id", it) }
        ts?.let { put("ts", it) }
    }

    fun withRequestId(id: String) = copy(requestId = id)
}

enum class Decision { ALLOW, CHALLENGE, BLOCK }

/** A decision: allow / challenge (which step-up) / block, the risk and the signals behind it. */
class AuthResponse(val raw: Map<String, Any?>) {
    val decisionId: String get() = raw["decision_id"] as String
    val decision: Decision get() = Decision.valueOf((raw["decision"] as String).uppercase())
    val riskScore: Double get() = (raw["risk_score"] as? Double) ?: Double.NaN
    /** sms_otp | passkey | bank_callback | cool_off, when the decision is a challenge */
    val challengeType: String? get() = raw["challenge_type"] as String?
    val messageEn: String get() = raw["message_en"] as String? ?: ""
    val messageHi: String get() = raw["message_hi"] as String? ?: ""
    val latencyMs: Double get() = (raw["latency_ms"] as? Double) ?: 0.0
    val degraded: Boolean get() = raw["degraded"] == true

    /** The top reasons (English, Hindi) for a challenge or block. */
    @Suppress("UNCHECKED_CAST")
    val reasons: List<Pair<String, String>>
        get() = (raw["reasons"] as? List<Map<String, Any?>>).orEmpty().map { (it["text_en"] as String) to (it["text_hi"] as String) }

    override fun toString() = "AuthResponse($decision, risk=$riskScore, challenge=$challengeType, ${latencyMs}ms)"
}

class ChallengeOutcome(val raw: Map<String, Any?>) {
    val decision: Decision get() = Decision.valueOf((raw["decision"] as String).uppercase())
    val passed: Boolean get() = raw["passed"] == true
    val deviceTrusted: Boolean get() = raw["device_trusted"] == true
    val messageEn: String get() = raw["message_en"] as String? ?: ""
}
