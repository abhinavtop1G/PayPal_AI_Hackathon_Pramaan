package com.pramaan.sdk.core

import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * Request signing as the gateway checks it (backend/security.py): `X-Signature: sha256=<hex HMAC-SHA256(secret,
 * "<unix seconds>.<raw body>")>` with `X-Timestamp`; accepted once, within 5 minutes.
 *
 * Keep the secret on your server. An app holding it can be reverse-engineered; sign in the bank backend that forwards
 * the SDK's request, or use the SDK client only against open demo paths.
 */
object Signing {
    fun hmacSha256Hex(secret: String, message: String): String {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(secret.toByteArray(Charsets.UTF_8), "HmacSHA256"))
        return mac.doFinal(message.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
    }

    fun headers(secret: String, body: String, unixSeconds: Long = System.currentTimeMillis() / 1000): Map<String, String> =
        mapOf("X-Timestamp" to unixSeconds.toString(), "X-Signature" to "sha256=" + hmacSha256Hex(secret, "$unixSeconds.$body"))
}
