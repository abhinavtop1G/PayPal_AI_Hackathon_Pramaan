package com.pramaan.sdk

import com.pramaan.sdk.core.AuthDevice
import com.pramaan.sdk.core.AuthRequest
import com.pramaan.sdk.core.AuthTransaction
import com.pramaan.sdk.core.Decision
import com.pramaan.sdk.core.Json
import com.pramaan.sdk.core.Signing
import com.pramaan.sdk.net.Fallback
import com.pramaan.sdk.net.PramaanClient
import com.pramaan.sdk.net.PramaanException
import com.sun.net.httpserver.HttpServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.net.InetSocketAddress
import java.util.concurrent.CopyOnWriteArrayList

/** The client against a local HTTP server: headers, signing, retries, fallbacks. */
class ClientTest {
    private data class Seen(val path: String, val headers: Map<String, String>, val body: String)

    private val seen = CopyOnWriteArrayList<Seen>()
    private val replies = ArrayDeque<Pair<Int, String>>()
    private val server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0).apply {
        createContext("/") { ex ->
            val body = ex.requestBody.readBytes().toString(Charsets.UTF_8)
            seen += Seen(ex.requestURI.path, ex.requestHeaders.entries.associate { it.key.lowercase() to it.value.first() }, body)
            val (status, text) = synchronized(replies) { replies.removeFirstOrNull() } ?: (200 to OK)
            if (status == 429) ex.responseHeaders.add("Retry-After", "2")
            val bytes = text.toByteArray()
            ex.sendResponseHeaders(status, bytes.size.toLong())
            ex.responseBody.use { it.write(bytes) }
        }
        start()
    }
    private val base = "http://127.0.0.1:${server.address.port}"
    private val req = AuthRequest("u1", AuthDevice("d1"), transaction = AuthTransaction(amount = 500.0, payeeId = "p1"))
    private val noSleep: (Long) -> Unit = {}

    @After
    fun stop() = server.stop(0)

    @Test
    fun sendsKeyAndSignatureOverTheExactBody() {
        val r = PramaanClient(base, apiKey = "k1", hmacSecret = "s1", sleeper = noSleep).authenticate(req)
        assertEquals(Decision.ALLOW, r.decision)
        val s = seen.single()
        assertEquals("/v1/authenticate", s.path)
        assertEquals("k1", s.headers["x-api-key"])
        val ts = s.headers.getValue("x-timestamp")
        assertEquals("sha256=" + Signing.hmacSha256Hex("s1", "$ts.${s.body}"), s.headers["x-signature"])
        @Suppress("UNCHECKED_CAST")
        val body = Json.parse(s.body) as Map<String, Any?>
        assertTrue((body["request_id"] as String).matches(Regex("[0-9a-f]{16}")))
        assertEquals(500.0, (body["transaction"] as Map<*, *>)["amount"])
    }

    @Test
    fun retries503AfterASecondKeepingTheRequestId() {
        replies += 503 to """{"detail":"busy"}"""
        val waits = mutableListOf<Long>()
        val r = PramaanClient(base, hmacSecret = "s", retries = 1, sleeper = { waits += it }).authenticate(req)
        assertEquals(Decision.ALLOW, r.decision)
        assertEquals(2, seen.size)
        assertTrue(waits.single() >= 1000)
        fun id(s: Seen) = (Json.parse(s.body) as Map<*, *>)["request_id"]
        assertEquals(id(seen[0]), id(seen[1]))
    }

    @Test
    fun doesNotRetryARejectedRequest() {
        replies += 422 to """{"detail":"bad"}"""
        try {
            PramaanClient(base, retries = 3, sleeper = noSleep).authenticate(req)
            fail("expected a 422")
        } catch (e: PramaanException) {
            assertEquals(PramaanException.Code.INVALID_REQUEST, e.code)
        }
        assertEquals(1, seen.size)
    }

    @Test
    fun fallsBackToAnOtpWhenTheServiceIsDown() {
        server.stop(0)
        val r = PramaanClient(base, retries = 0, timeoutMs = 500, sleeper = noSleep).authenticate(req.withRequestId("abc"))
        assertEquals(Decision.CHALLENGE, r.decision)
        assertEquals("sms_otp", r.challengeType)
        assertTrue(r.degraded)
        assertEquals("abc", r.decisionId)
    }

    @Test
    fun canFailOpenOrThrow() {
        replies += 503 to "{}"
        assertEquals(Decision.ALLOW, PramaanClient(base, retries = 0, fallback = Fallback.ALLOW, sleeper = noSleep).authenticate(req).decision)
        replies += 503 to "{}"
        try {
            PramaanClient(base, retries = 0, fallback = Fallback.THROW, sleeper = noSleep).authenticate(req)
            fail("expected an exception")
        } catch (e: PramaanException) {
            assertEquals(503, e.status)
        }
    }

    @Test
    fun honoursRetryAfter() {
        replies += 429 to "{}"
        val waits = mutableListOf<Long>()
        PramaanClient(base, retries = 1, sleeper = { waits += it }).health()
        assertEquals(2000L, waits.single())
    }

    @Test
    fun jsonRoundTrip() {
        val text = Json.write(mapOf("a" to listOf(1.5, null, true), "s" to "line\n\"q\" ₹ हिन्दी", "n" to Double.NaN))
        assertEquals("""{"a":[1.5,null,true],"s":"line\n\"q\" ₹ हिन्दी","n":null}""", text)
        assertEquals(mapOf("a" to listOf(1.5, null, true), "s" to "line\n\"q\" ₹ हिन्दी", "n" to null), Json.parse(text))
    }

    private companion object {
        const val OK = """{"decision_id":"x","user_id":"u1","decision":"allow","risk_score":0.001,"challenge_type":null,
            "message_en":"ok","message_hi":"ok","reasons":[],"latency_ms":12.5,"status":"ok"}"""
    }
}
