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
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.io.DataInputStream
import java.io.IOException
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.CopyOnWriteArrayList
import kotlin.concurrent.thread

/**
 * The client against a local HTTP server: headers, signing, retries, fallbacks. The server is a bare socket because
 * Android unit tests compile against android.jar, which has no com.sun.net.httpserver.
 */
class ClientTest {
    private data class Seen(val path: String, val headers: Map<String, String>, val body: String)

    private val seen = CopyOnWriteArrayList<Seen>()
    private val replies = ArrayDeque<Pair<Int, String>>()
    private val server = ServerSocket(0, 50, InetAddress.getByName("127.0.0.1"))
    private val worker = thread(isDaemon = true, name = "client-test-server") {
        while (!server.isClosed) {
            val socket = try { server.accept() } catch (e: IOException) { break }
            runCatching { socket.use(::exchange) }
        }
    }
    private val base = "http://127.0.0.1:${server.localPort}"
    private val req = AuthRequest("u1", AuthDevice("d1"), transaction = AuthTransaction(amount = 500.0, payeeId = "p1"))
    private val noSleep: (Long) -> Unit = {}

    /** One request and reply per connection (Connection: close), which is all HttpURLConnection needs. */
    private fun exchange(socket: Socket) {
        val input = DataInputStream(socket.getInputStream().buffered())
        fun line(): String {
            val b = ByteArrayOutputStream()
            while (true) {
                val c = input.read()
                if (c == -1 || c == '\n'.code) break
                if (c != '\r'.code) b.write(c)
            }
            return String(b.toByteArray(), Charsets.UTF_8)
        }
        val path = line().split(" ")[1].substringBefore('?')
        val headers = generateSequence(::line).takeWhile { it.isNotEmpty() }
            .associate { it.substringBefore(':').trim().lowercase() to it.substringAfter(':').trim() }
        val body = ByteArray(headers["content-length"]?.toInt() ?: 0).also(input::readFully)
        seen += Seen(path, headers, String(body, Charsets.UTF_8))

        val (status, text) = synchronized(replies) { replies.removeFirstOrNull() } ?: (200 to OK)
        val bytes = text.toByteArray()
        val head = buildString {
            append("HTTP/1.1 $status Status\r\nContent-Type: application/json\r\nContent-Length: ${bytes.size}\r\nConnection: close\r\n")
            if (status == 429) append("Retry-After: 2\r\n")
            append("\r\n")
        }
        socket.getOutputStream().apply { write(head.toByteArray()); write(bytes); flush() }
    }

    @After
    fun stop() {
        server.close()
        worker.join(1000)
    }

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
        server.close()
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
