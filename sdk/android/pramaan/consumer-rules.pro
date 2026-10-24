# The SDK uses no reflection; keep its public API names readable in host apps' stack traces.
-keep public class com.pramaan.sdk.Pramaan { public *; }
-keep public class com.pramaan.sdk.PramaanConfig { *; }
-keep public class com.pramaan.sdk.core.** { public *; }
-keep public class com.pramaan.sdk.net.** { public *; }
