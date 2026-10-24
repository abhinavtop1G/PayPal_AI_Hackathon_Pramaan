package com.pramaan.sdk

import com.pramaan.sdk.core.GestureSpec
import com.pramaan.sdk.core.Json
import com.pramaan.sdk.core.KeystrokeRecorder
import com.pramaan.sdk.core.KeystrokeSpec
import com.pramaan.sdk.core.ScreenSize
import com.pramaan.sdk.core.Signing
import com.pramaan.sdk.core.TouchPoint
import com.pramaan.sdk.core.TouchTracker
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.io.File

/** The SDK's on-device math against the training pipeline's own outputs (sdk/spec/make_golden.py). */
@Suppress("UNCHECKED_CAST")
class GoldenTest {
    private val golden = Json.parse(File(System.getProperty("pramaan.golden") ?: "../../spec/golden.json")
        .readText(Charsets.UTF_8)) as Map<String, Any?>
    private val touch = golden["touch"] as Map<String, Any?>
    private val keys = golden["keystrokes"] as Map<String, Any?>

    private fun Map<String, Any?>.d(k: String) = (this[k] as Number).toDouble()

    @Test
    fun featureOrderMatchesTheModel() {
        assertEquals(touch["feature_names"], GestureSpec.FEATURES)
    }

    @Test
    fun gesturesMatchTheTrainingPipeline() {
        val screen = touch["screen"] as Map<String, Any?>
        val tr = TouchTracker(ScreenSize(screen.d("width"), screen.d("height")))
        for (s in touch["acc"] as List<Map<String, Any?>>) tr.acc.push(s.d("t"), s.d("x"), s.d("y"), s.d("z"))
        for (s in touch["gyr"] as List<Map<String, Any?>>) tr.gyr.push(s.d("t"), s.d("x"), s.d("y"), s.d("z"))
        for (f in touch["frames"] as List<Map<String, Any?>>) {
            tr.rotated = f.d("orientation") != 0.0
            val p = TouchPoint(f.d("t"), f.d("x"), f.d("y"), f.d("size"))
            if (f.d("pointer_count") > 1) tr.down(1, p)
            when (f.d("action").toInt()) {
                0 -> tr.down(0, p)
                1 -> tr.up(0, p)
                else -> tr.move(0, p)
            }
        }
        tr.settle(Double.MAX_VALUE, force = true)
        val want = touch["features"] as List<Map<String, Any?>>
        val got = tr.window()
        assertEquals(want.size, got.size)
        for ((i, w) in want.withIndex()) {
            for (k in GestureSpec.FEATURES) {
                val wv = w[k] as Double?
                if (wv == null) assertNull("$i.$k", got[i][k]) else assertEquals("$i.$k", wv, got[i][k]!!, 1e-9)
            }
        }
    }

    @Test
    fun keystrokeTimingsMatchColumns() {
        val perKey = (keys["per_key"] as List<Map<String, Any?>>).map { KeystrokeSpec.KeyTiming(it.d("down"), it.d("up")) }
        assertEquals(keys["timings"], KeystrokeSpec.timings(perKey))
    }

    @Test
    fun keystrokeRecorderRecoversTheAttemptFromRawEvents() {
        var got: List<Double>? = null
        val rec = KeystrokeRecorder(onAttempt = { got = it.timings })
        for (e in keys["events"] as List<Map<String, Any?>>) {
            if (e["type"] == "down") rec.down(e["code"] as String, e.d("t"), e["repeat"] == true)
            else rec.up(e["code"] as String, e.d("t"))
        }
        assertEquals(keys["timings"], got)
        assertEquals(KeystrokeSpec.KEYS, rec.lastAttempt?.keys)
    }

    @Test
    fun signatureMatchesTheGateway() {
        val s = golden["signing"] as Map<String, Any?>
        val h = Signing.headers(s["secret"] as String, s["body"] as String, (s["timestamp"] as Double).toLong())
        assertEquals(s["headers"], h)
    }
}
