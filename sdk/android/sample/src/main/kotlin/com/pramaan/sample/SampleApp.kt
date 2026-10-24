package com.pramaan.sample

import android.app.Application
import com.pramaan.sdk.Pramaan
import com.pramaan.sdk.PramaanConfig

class SampleApp : Application() {
    override fun onCreate() {
        super.onCreate()
        // The demo calls a local API directly (10.0.2.2 is the host machine from the Android emulator). A bank app
        // would send Pramaan.collect()'s request to its own backend, which holds the API key and signing secret.
        Pramaan.init(this, PramaanConfig(baseUrl = API_URL))
    }

    companion object {
        const val API_URL = "http://10.0.2.2:8000"
    }
}
