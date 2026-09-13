package ru.dietolog.healthsync

import android.content.Context

data class HealthSyncSettings(
    val serverUrl: String,
    val token: String,
    val telegramId: Long,
)

object HealthSyncConfig {
    private const val PREFS = "dietolog_health_sync"
    private const val SERVER_URL = "server_url"
    private const val TOKEN = "token"
    private const val TELEGRAM_ID = "telegram_id"

    fun load(context: Context): HealthSyncSettings {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        return HealthSyncSettings(
            serverUrl = prefs.getString(SERVER_URL, "") ?: "",
            token = prefs.getString(TOKEN, "") ?: "",
            telegramId = prefs.getLong(TELEGRAM_ID, 0L),
        )
    }

    fun save(context: Context, settings: HealthSyncSettings) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(SERVER_URL, settings.serverUrl.trim().trimEnd('/'))
            .putString(TOKEN, settings.token.trim())
            .putLong(TELEGRAM_ID, settings.telegramId)
            .apply()
    }
}
