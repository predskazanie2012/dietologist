package ru.dietolog.healthsync

import okhttp3.MediaType.Companion.toMediaType
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

class DietologApiClient {
    private val http = OkHttpClient.Builder().followRedirects(false).followSslRedirects(false).build()
    private val jsonType = "application/json; charset=utf-8".toMediaType()

    fun sync(settings: HealthSyncSettings, payload: HealthPayload) {
        require(settings.serverUrl.isNotBlank()) { "Server URL is empty" }
        val server = settings.serverUrl.toHttpUrl()
        require(server.isHttps && server.username.isEmpty() && server.password.isEmpty()) { "Use an HTTPS endpoint without embedded credentials" }
        require(settings.token.isNotBlank()) { "Sync token is empty" }
        require(settings.telegramId > 0) { "Telegram ID is empty" }

        val body = JSONObject()
            .put("telegram_id", settings.telegramId)
            .put("date", payload.date)
            .put("steps", payload.steps)
            .put("active_calories", payload.activeCalories)
            .put("total_calories", payload.totalCalories)
            .put("distance_m", payload.distanceMeters)
            .put("sleep_minutes", payload.sleepMinutes)
            .put("avg_heart_rate", payload.avgHeartRate)
            .put("source", "health_connect")
            .put(
                "raw",
                JSONObject()
                    .put("android_source", "health_connect")
                    .put("app", "Dietolog Health Sync")
            )
            .toString()
            .toRequestBody(jsonType)

        val request = Request.Builder()
            .url("${settings.serverUrl}/integrations/health/activity")
            .header("X-Health-Sync-Token", settings.token)
            .post(body)
            .build()

        http.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                throw IllegalStateException("Server returned HTTP ${response.code}: ${response.body?.string()}")
            }
        }
    }
}
