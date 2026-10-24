package com.pramaan.sdk

import com.pramaan.sdk.core.AuthBehaviour
import com.pramaan.sdk.core.AuthDevice
import com.pramaan.sdk.core.AuthNetwork
import com.pramaan.sdk.core.AuthRequest
import com.pramaan.sdk.core.AuthTransaction
import com.pramaan.sdk.core.KeystrokeSpec
import com.pramaan.sdk.core.ScreenSize
import com.pramaan.sdk.core.TouchPoint
import com.pramaan.sdk.core.TouchTracker
import com.pramaan.sdk.net.Fallback
import com.pramaan.sdk.net.PramaanClient
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import kotlin.random.Random

/** Against a running service: `PRAMAAN_API=http://127.0.0.1:8000 gradle :pramaan:testDebugUnitTest` (skipped otherwise). */
class LiveTest {
    private val api: String? = System.getProperty("pramaan.api")

    private fun gestures(n: Int, seed: Int): List<Map<String, Double?>> {
        val rnd = Random(seed)
        val tr = TouchTracker(ScreenSize(1080.0, 2400.0), keep = n)
        var t = 1000.0
        repeat(n) { i ->
            var k = t - 200
            while (k < t + 600) {
                tr.acc.push(k, 0.2 * rnd.nextDouble(), 0.3 * rnd.nextDouble(), 9.7 + 0.2 * rnd.nextDouble()); k += 10
            }
            val steps = if (i % 3 == 0) 2 else 12
            for (s in 0..steps) {
                val p = TouchPoint(t + s * 16, 500.0, 1600.0 - (if (steps > 2) s * 60.0 else rnd.nextDouble() * 4), 0.022)
                when (s) { 0 -> tr.down(0, p); steps -> tr.up(0, p); else -> tr.move(0, p) }
            }
            t += 700 + rnd.nextDouble() * 500
        }
        tr.settle(Double.MAX_VALUE, force = true)
        return tr.window()
    }

    private fun attempt(hold: Double, flight: Double, noise: Double, seed: Int): List<Double> {
        val rnd = Random(seed)
        var t = 0.0
        val keys = List(KeystrokeSpec.KEYS) {
            val down = t
            t += flight * (1 + (rnd.nextDouble() - 0.5) * 2 * noise)
            KeystrokeSpec.KeyTiming(down * 1000, (down + hold * (1 + (rnd.nextDouble() - 0.5) * 2 * noise)) * 1000)
        }
        return KeystrokeSpec.timings(keys)
    }

    @Test
    fun scoresAnSdkBuiltRequestAndEnrolsTyping() {
        assumeTrue("set PRAMAAN_API to run", api != null)
        val c = PramaanClient(api!!, timeoutMs = 10_000, retries = 0, fallback = Fallback.THROW)
        val r = c.authenticate(AuthRequest(
            userId = "demo-asha",
            device = AuthDevice("asha-pixel-7"),
            network = AuthNetwork(ip = "49.36.112.45", lat = 30.901, lon = 75.857, city = "Ludhiana"),
            behaviour = AuthBehaviour(gestures = gestures(12, 1), keystrokes = attempt(0.09, 0.2, 0.2, 7),
                timeToSubmitS = 14.0, inputEvents = 30),
            transaction = AuthTransaction(amount = 640.0, payeeId = "kirana-sharma", payeeIsMerchant = true),
        ))
        val features = r.raw["features"] as Map<*, *>
        assertNotNull("touch reached the model", features["bio_dev"])
        assertNotNull("typing reached the model", features["typing_dev"])

        val uid = "android-live-" + System.currentTimeMillis()
        assertEquals(true, c.enrollTyping(uid, List(8) { attempt(0.09, 0.2, 0.08, 11 + it) })["enrolled"])
        val me = c.verifyTyping(uid, attempt(0.09, 0.2, 0.08, 99))["typing_deviation"] as Double
        val other = c.verifyTyping(uid, attempt(0.16, 0.42, 0.25, 5))["typing_deviation"] as Double
        assertTrue("owner closer than someone else: $me vs $other", me < other)
    }
}
