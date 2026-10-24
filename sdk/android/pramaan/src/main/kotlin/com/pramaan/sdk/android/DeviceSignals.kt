package com.pramaan.sdk.android

import android.content.Context
import android.content.pm.PackageManager
import android.hardware.display.DisplayManager
import android.os.Build
import android.provider.Settings
import android.telephony.SubscriptionManager
import java.io.File
import java.security.MessageDigest

/**
 * The device signals the risk model reads, from the phone itself:
 *   is_rooted            su binaries, test-keys build, root-manager apps
 *   is_emulator          build properties of the Android emulator, Genymotion and other virtual devices
 *   remote_access_app    a remote-control app (AnyDesk, TeamViewer QuickSupport, RustDesk, AirDroid...) is driving the
 *                        phone: its accessibility service is on, or it is installed while the screen is being captured
 *   screen_share_active  this app's screen is being recorded / shared (Android 15+), or mirrored to a cast display
 *   sim_change_hours     hours since the SIM in this phone changed (first seen by this install); a telecom SIM-swap
 *                        API can supply it instead (PramaanConfig.simChangeHours)
 * Client-side checks can be fooled on a compromised phone; production pairs them with Play Integrity attestation.
 */
object DeviceSignals {
    /** Remote-control / screen-sharing apps used in "support agent" scams. Declared in the manifest's <queries>. */
    val REMOTE_ACCESS_PACKAGES = listOf(
        "com.anydesk.anydeskandroid", "com.teamviewer.quicksupport.market", "com.teamviewer.host.market",
        "com.teamviewer.teamviewer.market.mobile", "com.carriez.flutter_hbb", "com.sand.airdroid", "com.sand.airdroidbiz",
        "com.splashtop.sos", "com.splashtop.streamer.addon.knox", "com.zoho.assist.agent", "com.aomei.anyviewer",
        "com.rsupport.mobizen.sec", "com.realvnc.server",
    )
    private val ROOT_PACKAGES = listOf("com.topjohnwu.magisk", "eu.chainfire.supersu", "com.koushikdutta.superuser",
        "com.noshufou.android.su", "com.kingroot.kinguser", "me.weishu.kernelsu")
    private val SU_PATHS = listOf("/system/bin/su", "/system/xbin/su", "/sbin/su", "/su/bin/su", "/data/local/xbin/su",
        "/data/local/bin/su", "/system/sd/xbin/su", "/system/bin/failsafe/su", "/data/local/su", "/debug_ramdisk/su")

    fun isRooted(ctx: Context): Boolean =
        Build.TAGS?.contains("test-keys") == true ||
            SU_PATHS.any { runCatching { File(it).exists() }.getOrDefault(false) } ||
            ROOT_PACKAGES.any { installed(ctx, it) }

    fun isEmulator(): Boolean {
        val fp = Build.FINGERPRINT.orEmpty()
        val model = Build.MODEL.orEmpty()
        val hw = Build.HARDWARE.orEmpty()
        val product = Build.PRODUCT.orEmpty()
        return fp.startsWith("generic") || fp.startsWith("unknown") || fp.contains("emulator") || fp.contains("sdk_gphone") ||
            model.contains("google_sdk") || model.contains("Emulator") || model.contains("Android SDK built for") ||
            Build.MANUFACTURER.orEmpty().contains("Genymotion") ||
            hw == "goldfish" || hw == "ranchu" || hw.contains("vbox") ||
            product.startsWith("sdk") || product.contains("emulator") || product.contains("simulator") || product == "vbox86p" ||
            (Build.BRAND.orEmpty().startsWith("generic") && Build.DEVICE.orEmpty().startsWith("generic"))
    }

    /** Remote-control apps installed on the phone (needs the <queries> entries in the SDK manifest). */
    fun remoteAccessInstalled(ctx: Context): List<String> = REMOTE_ACCESS_PACKAGES.filter { installed(ctx, it) }

    /** Remote-control apps whose accessibility service is switched on: they can read and tap the screen. */
    fun remoteAccessControlling(ctx: Context): List<String> {
        val enabled = Settings.Secure.getString(ctx.contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES).orEmpty()
        return REMOTE_ACCESS_PACKAGES.filter { pkg -> enabled.split(':').any { it.startsWith("$pkg/") } }
    }

    /** A cast / presentation display is connected (screen mirrored to a TV or a capture device). */
    fun castDisplayConnected(ctx: Context): Boolean {
        val dm = ctx.getSystemService(Context.DISPLAY_SERVICE) as? DisplayManager ?: return false
        return dm.getDisplays(DisplayManager.DISPLAY_CATEGORY_PRESENTATION).isNotEmpty()
    }

    /**
     * Hours since this install first saw the phone's SIM change; null until a change has been seen. Uses the default
     * subscription ID, which needs no permission and changes when a different SIM goes in.
     */
    fun simChangeHours(ctx: Context, nowMs: Long = System.currentTimeMillis()): Double? {
        val prefs = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val sub = SubscriptionManager.getDefaultSubscriptionId()
        val seen = if (prefs.contains(KEY_SUB)) prefs.getInt(KEY_SUB, Int.MIN_VALUE) else null
        when {
            seen == null -> prefs.edit().putInt(KEY_SUB, sub).apply()
            seen != sub -> prefs.edit().putInt(KEY_SUB, sub).putLong(KEY_SUB_CHANGED, nowMs).apply()
        }
        val changed = prefs.getLong(KEY_SUB_CHANGED, -1L)
        return if (changed < 0) null else (nowMs - changed).coerceAtLeast(0) / 3_600_000.0
    }

    /** A stable ID for this app on this device (ANDROID_ID is per signing key and user), hashed so it carries nothing
     *  else; falls back to a random install ID. */
    fun deviceId(ctx: Context): String {
        val prefs = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        prefs.getString(KEY_ID, null)?.let { return it }
        val androidId = Settings.Secure.getString(ctx.contentResolver, Settings.Secure.ANDROID_ID)
        val seed = androidId ?: java.util.UUID.randomUUID().toString()
        val digest = MessageDigest.getInstance("SHA-256").digest("${ctx.packageName}:$seed".toByteArray())
        val id = "android-" + digest.take(10).joinToString("") { "%02x".format(it) }
        prefs.edit().putString(KEY_ID, id).apply()
        return id
    }

    private fun installed(ctx: Context, pkg: String): Boolean = try {
        if (Build.VERSION.SDK_INT >= 33) ctx.packageManager.getPackageInfo(pkg, PackageManager.PackageInfoFlags.of(0))
        else @Suppress("DEPRECATION") ctx.packageManager.getPackageInfo(pkg, 0)
        true
    } catch (e: PackageManager.NameNotFoundException) {
        false
    }

    private const val PREFS = "pramaan.device"
    private const val KEY_ID = "device_id"
    private const val KEY_SUB = "sim_sub_id"
    private const val KEY_SUB_CHANGED = "sim_changed_at"
}
