# Limitations and integration requirements

Local API startup, database initialization, food catalog and access boundaries were checked. Live Telegram/AI conversations and Android device synchronization were not independently exercised.

The local requirements include the API, Telegram and AI provider clients. The Android Health Connect companion has its own [setup notes](mobile/health-sync-android/README.md).

Keep web services bound to `127.0.0.1`. Hosting this application for multiple users requires authentication and separate storage and resource limits.
