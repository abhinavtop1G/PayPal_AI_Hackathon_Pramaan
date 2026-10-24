package com.pramaan.sdk.net

import com.pramaan.sdk.core.AuthRequest
import com.pramaan.sdk.core.AuthResponse
import com.pramaan.sdk.core.ChallengeOutcome
import com.pramaan.sdk.core.GestureFeatures
import com.pramaan.sdk.core.Json
import com.pramaan.sdk.core.Signing
import java.io.IOException
import java.net.HttpURLConnection
import java.net.SocketTimeoutException
import java.net.URL
import java.util.UUID
import java.util.concurrent.Executor
import java.util.concurrent.Executors
import kotlin.random.Random

/** What authenticate() answers when the service cannot be reached after the retries. */
enum class Fallback {
    /** step up with an SMS OTP: an outage costs friction, not fraud (default) */
    CHALLENGE,
    /** let the payment through (fail open) */
    ALLOW,
    /** throw [PramaanException] and let the caller decide */
    THROW,
}

class PramaanException(
    message: String,
    val code: Code,
    val status: Int? = null,
    val body: String? = null,
    val retryAfterS: Long? = null,
) : IOException(message) {
    enum class Code { TIMEOUT, NETWORK, RATE_LIMITED, UNAUTHORIZED, INVALID_REQUEST, NOT_FOUND, SERVER }

    val retryable: Boolean
        get() = code == Code.TIMEOUT || code == Code.NETWORK || code == Code.RATE_LIMITED ||
            (code == Code.SERVER && status in setOf(502, 503, 504))
}

/**
 * Client for the PRAMAAN API. Calls block: use them off the main thread, or the *Async variants. Retries are spaced at
 * least a second apart because the signature covers the timestamp in whole seconds and the gateway rejects a repeated
 * signature as a replay; the request_id stays the same across retries.
 *
 * In production the app sends the SDK's request to the bank's backend, which calls PRAMAAN with the API key and
 * signing secret; this client is that backend's client (Kotlin / JVM) and the app's client for open demo paths.
 */
class PramaanClient(
    baseUrl: String,
    private val apiKey: String? = null,
    private val hmacSecret: String? = null,
    private val timeoutMs: Int = 3000,
    private val retries: Int = 1,
    private val fallback: Fallback = Fallback.CHALLENGE,
    private val executor: Executor = DEFAULT_EXECUTOR,
    private val sleeper: (Long) -> Unit = { Thread.sleep(it) },
) {
    private val base = baseUrl.trimEnd('/')

    /** Decide a login or payment; when the service is unreachable the [fallback] answers, marked `degraded`. */
    fun authenticate(request: AuthRequest): AuthResponse {
        val req = if (request.requestId == null) request.withRequestId(newRequestId()) else request
        return try {
            AuthResponse(call("POST", "/v1/authenticate", Json.write(req)))
        } catch (e: PramaanException) {
            if (fallback == Fallback.THROW || !e.retryable) throw e
            degraded(req, fallback)
        }
    }

    /** passed → allow (a passkey or bank call-back also trusts the device); failed → block + 30-minute lock. */
    fun verifyChallenge(decisionId: String, passed: Boolean): ChallengeOutcome =
        ChallengeOutcome(call("POST", "/v1/challenge/verify", Json.write(mapOf("decision_id" to decisionId, "passed" to passed))))

    fun enrollTyping(userId: String, attempts: List<List<Double>>): Map<String, Any?> =
        call("POST", "/v1/keystroke/enroll", Json.write(mapOf("user_id" to userId, "attempts" to attempts)))

    fun verifyTyping(userId: String, attempt: List<Double>): Map<String, Any?> =
        call("POST", "/v1/keystroke/verify", Json.write(mapOf("user_id" to userId, "attempt" to attempt)))

    fun enrollTouch(userId: String, gestures: List<GestureFeatures>): Map<String, Any?> =
        call("POST", "/v1/biometrics/enroll", Json.write(mapOf("user_id" to userId, "gestures" to gestures)))

    fun verifyTouch(userId: String, gestures: List<GestureFeatures>): Map<String, Any?> =
        call("POST", "/v1/biometrics/verify", Json.write(mapOf("user_id" to userId, "gestures" to gestures)))

    fun health(): Map<String, Any?> = call("GET", "/health", null)

    fun authenticateAsync(request: AuthRequest, callback: (Result<AuthResponse>) -> Unit) =
        executor.execute { callback(runCatching { authenticate(request) }) }

    fun verifyChallengeAsync(decisionId: String, passed: Boolean, callback: (Result<ChallengeOutcome>) -> Unit) =
        executor.execute { callback(runCatching { verifyChallenge(decisionId, passed) }) }

    /** Any endpoint, with the client's auth, signing, timeout and retries. */
    @Suppress("UNCHECKED_CAST")
    fun call(method: String, path: String, body: String?): Map<String, Any?> {
        var last: PramaanException? = null
        for (attempt in 0..retries) {
            if (attempt > 0) sleeper(last?.retryAfterS?.times(1000) ?: (1000L shl (attempt - 1)) + Random.nextLong(250))
            try {
                val text = once(method, path, body)
                val v = Json.parse(text)
                return v as? Map<String, Any?> ?: mapOf("items" to v)
            } catch (e: PramaanException) {
                if (!e.retryable) throw e
                last = e
            }
        }
        throw last!!
    }

    private fun once(method: String, path: String, body: String?): String {
        val conn = try {
            URL(base + path).openConnection() as HttpURLConnection
        } catch (e: IOException) {
            throw PramaanException("$path: ${e.message}", PramaanException.Code.NETWORK)
        }
        try {
            conn.requestMethod = method
            conn.connectTimeout = timeoutMs
            conn.readTimeout = timeoutMs
            conn.setRequestProperty("Accept", "application/json")
            apiKey?.let { conn.setRequestProperty("X-API-Key", it) }
            hmacSecret?.let { s -> Signing.headers(s, body ?: "").forEach { (k, v) -> conn.setRequestProperty(k, v) } }
            if (body != null) {
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                conn.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            }
            val status = conn.responseCode
            val text = (if (status in 200..299) conn.inputStream else conn.errorStream)
                ?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: ""
            if (status in 200..299) return text
            throw PramaanException("$path: $status $text", codeFor(status), status, text,
                conn.getHeaderField("Retry-After")?.toLongOrNull())
        } catch (e: SocketTimeoutException) {
            throw PramaanException("$path: no answer in $timeoutMs ms", PramaanException.Code.TIMEOUT)
        } catch (e: PramaanException) {
            throw e
        } catch (e: IOException) {
            throw PramaanException("$path: ${e.message}", PramaanException.Code.NETWORK)
        } finally {
            conn.disconnect()
        }
    }

    companion object {
        private val DEFAULT_EXECUTOR: Executor = Executors.newCachedThreadPool { r ->
            Thread(r, "pramaan-net").apply { isDaemon = true }
        }

        fun newRequestId(): String = UUID.randomUUID().toString().replace("-", "").take(16)

        private fun codeFor(status: Int) = when (status) {
            429 -> PramaanException.Code.RATE_LIMITED
            401, 403, 409 -> PramaanException.Code.UNAUTHORIZED
            404 -> PramaanException.Code.NOT_FOUND
            400, 422 -> PramaanException.Code.INVALID_REQUEST
            else -> PramaanException.Code.SERVER
        }

        private fun degraded(req: AuthRequest, mode: Fallback): AuthResponse {
            val challenge = mode == Fallback.CHALLENGE
            return AuthResponse(mapOf(
                "decision_id" to req.requestId, "user_id" to req.userId, "decision" to if (challenge) "challenge" else "allow",
                "risk_score" to Double.NaN, "challenge_type" to if (challenge) "sms_otp" else null, "rule" to "service_unreachable",
                "message_en" to if (challenge) "Verify with the one-time password sent to your registered number." else "Payment approved.",
                "message_hi" to if (challenge) "अपने पंजीकृत नंबर पर भेजे गए वन-टाइम पासवर्ड से पुष्टि करें।" else "भुगतान स्वीकृत।",
                "reasons" to emptyList<Any>(), "model_version" to "fallback", "latency_ms" to 0.0, "degraded" to true,
            ))
        }
    }
}
