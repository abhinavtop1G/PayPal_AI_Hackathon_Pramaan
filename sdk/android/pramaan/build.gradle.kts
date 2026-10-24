plugins {
    id("com.android.library")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.pramaan.sdk"
    compileSdk = 35

    defaultConfig {
        minSdk = 24
        consumerProguardFiles("consumer-rules.pro")
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    sourceSets["main"].java.srcDirs("src/main/kotlin")
    sourceSets["test"].java.srcDirs("src/test/kotlin")

    testOptions {
        unitTests.all {
            // golden vectors shared with the web SDK, generated from the training pipeline (sdk/spec/make_golden.py)
            it.systemProperty("pramaan.golden", rootProject.file("../spec/golden.json").absolutePath)
            System.getenv("PRAMAAN_API")?.let { api -> it.systemProperty("pramaan.api", api) }
        }
    }
}

kotlin {
    jvmToolchain(17)
}

dependencies {
    // no runtime dependencies: the SDK uses only the Android framework
    testImplementation("junit:junit:4.13.2")
}
