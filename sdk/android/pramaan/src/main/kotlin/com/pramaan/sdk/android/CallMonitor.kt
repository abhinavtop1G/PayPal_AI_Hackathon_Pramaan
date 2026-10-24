package com.pramaan.sdk.android

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioManager
import android.net.Uri
import android.provider.CallLog
import android.provider.ContactsContract

/**
 * Is the customer on a call with someone who is not in their contacts? Coached victims ("police", "bank support")
 * are kept on the line while they pay. Being on a call needs no permission (the audio mode: cellular call or a VoIP
 * call in WhatsApp, Skype...). Whether the caller is a contact needs READ_CALL_LOG + READ_CONTACTS; without them a
 * call counts as unknown when [unverifiedIsUnknown] is true.
 */
class CallMonitor(private val ctx: Context, private val unverifiedIsUnknown: Boolean = true) {
    enum class Kind { NONE, CELLULAR, VOIP }

    fun kind(): Kind {
        val am = ctx.getSystemService(Context.AUDIO_SERVICE) as? AudioManager ?: return Kind.NONE
        return when (am.mode) {
            AudioManager.MODE_IN_CALL, AudioManager.MODE_RINGTONE -> Kind.CELLULAR
            AudioManager.MODE_IN_COMMUNICATION -> Kind.VOIP
            else -> Kind.NONE
        }
    }

    fun unknownCallActive(): Boolean = when (kind()) {
        Kind.NONE -> false
        Kind.VOIP -> unverifiedIsUnknown // VoIP callers are not in the call log
        Kind.CELLULAR -> lastCallerIsContact()?.not() ?: unverifiedIsUnknown
    }

    /** true / false when it can be checked, null without the permissions or a recent call. */
    private fun lastCallerIsContact(): Boolean? {
        if (!granted(Manifest.permission.READ_CALL_LOG) || !granted(Manifest.permission.READ_CONTACTS)) return null
        val number = runCatching {
            ctx.contentResolver.query(CallLog.Calls.CONTENT_URI, arrayOf(CallLog.Calls.NUMBER), null, null,
                "${CallLog.Calls.DATE} DESC")?.use { c -> if (c.moveToFirst()) c.getString(0) else null }
        }.getOrNull() ?: return null
        val uri = Uri.withAppendedPath(ContactsContract.PhoneLookup.CONTENT_FILTER_URI, Uri.encode(number))
        return runCatching {
            ctx.contentResolver.query(uri, arrayOf(ContactsContract.PhoneLookup._ID), null, null, null)?.use { it.count > 0 }
        }.getOrNull()
    }

    private fun granted(p: String) = ctx.checkSelfPermission(p) == PackageManager.PERMISSION_GRANTED
}
