# PRAMAAN Android SDK (`com.pramaan.sdk`)

Kotlin library for Android 7+ (API 24, compiled against 35) with no dependencies beyond the framework. It watches the
app's activities and builds the request `POST /v1/authenticate` scores, including the device signals only a phone can
see.

```kotlin
class App : Application() {
    override fun onCreate() {
        super.onCreate()
        Pramaan.init(this, PramaanConfig(consent = userConsented))   // every activity's touches are observed
    }
}

// payment screen
Pramaan.get().startFlow()
val pad = Pramaan.get().pinPad(this, maxLength = 6) { pin -> submit(pin) }   // records key timing, never digits

// on submit, off the main thread; send it to your backend, which adds the API key + signature
val request = Pramaan.get().collect(userId, transaction = AuthTransaction(amount = 2500.0, payeeId = "kirana-sharma"))
```

| signal | how |
|---|---|
| touch gestures | a pass-through `Window.Callback` on each activity: one point per `MotionEvent` (as HMOG logged), `getSize()` for contact size; accelerometer (with gravity) and gyroscope at 100 Hz while an activity is in the foreground, sensor time moved onto the touch clock; 21 features per gesture, never coordinates |
| typing rhythm | `PinPadView` (system keyboards do not report key timing to apps) or `keyListener()` for hardware keyboards; 31 timings for 11 keys |
| unknown caller | `AudioManager` mode (cellular or VoIP call) without permissions; the caller is checked against contacts when the app holds `READ_CALL_LOG` + `READ_CONTACTS` |
| root | su binaries, test-keys build, root-manager packages |
| emulator | Android emulator / Genymotion / VirtualBox build properties |
| remote-control app | AnyDesk, TeamViewer QuickSupport, RustDesk, AirDroid, Splashtop… with its accessibility service on, or installed while the screen is captured |
| screen sharing | Android 15 `addScreenRecordingCallback` (`DETECT_SCREEN_RECORDING`, a normal permission), cast / presentation displays |
| SIM change | the default subscription ID changing under this install; or a telecom SIM-swap API through `PramaanConfig.simChangeHours` |
| install ID | SHA-256 of package + `ANDROID_ID`, stored once |

Client-side checks can be fooled on a compromised phone: pair them with Play Integrity attestation in production.

`PramaanClient` (also usable on a JVM backend) signs requests, retries ≥ 1 s apart with the same `request_id`, and
falls back to an SMS OTP when the service is down (`Fallback.CHALLENGE`, or `ALLOW` / `THROW`).

## Layout

```
pramaan/src/main/kotlin/com/pramaan/sdk/
  Pramaan.kt                 entry point: init, attach, startFlow, pinPad, keyListener, device(), collect()
  core/                      plain Kotlin, tested on the JVM: gesture features, motion buffer, touch tracker,
                             keystroke timings, JSON, signing, request / response models
  net/PramaanClient.kt       HttpURLConnection client
  android/                   touch + sensor capture, device signals, call monitor, PIN pad
pramaan/src/test/kotlin/     golden vectors (sdk/spec/golden.json), client against a local HTTP server, live test
sample/                      a UPI-style payment screen wired to the SDK (talks to http://10.0.2.2:8000)
```

```bash
gradle :pramaan:testDebugUnitTest                                   # JDK 17, Android SDK 35
PRAMAAN_API=http://127.0.0.1:8000 gradle :pramaan:testDebugUnitTest # + the live test
gradle :sample:installDebug
```

The sources were compile-checked against `android.jar` (API 35) and the 13 JVM tests run with the Kotlin 2.2 compiler
directly; the Gradle build itself has not been run on the development machine (no Android SDK installed there).
