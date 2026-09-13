# Dietologist Health Sync — Android source

A Kotlin companion that reads selected Health Connect activity data and sends it to a configured Dietologist integration endpoint.

Open this folder in Android Studio and let it resolve the declared Gradle plugins and Android SDK. No local.properties, signing keystore, APK, device settings or real server address is included. The original project has no Gradle wrapper in this repository; an Android Studio/Gradle setup is required.

The client disables Android backup, disallows cleartext traffic, requires an HTTPS endpoint and disables redirects for requests carrying the sync token. These source changes were inspected but not built or tested on a device.

This repository's local API accepts local requests only. Connecting a physical phone requires a separately configured, authenticated HTTPS backend; the local request guard must not simply be removed to expose an unprotected service. Full Android integration and Gradle dependency security are outside the completed runtime checks.
