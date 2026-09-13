package ru.dietolog.healthsync

import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.health.connect.client.PermissionController
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    private lateinit var health: HealthConnectRepository
    private lateinit var serverUrl: EditText
    private lateinit var token: EditText
    private lateinit var telegramId: EditText
    private lateinit var status: TextView

    private val permissionLauncher = registerForActivityResult(
        PermissionController.createRequestPermissionResultContract()
    ) { granted: Set<String> ->
        status.text = if (granted.containsAll(health.permissions)) {
            "Разрешения Health Connect выданы."
        } else {
            "Не все разрешения выданы. Автосинхронизация может не работать."
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        health = HealthConnectRepository(this)
        val settings = HealthSyncConfig.load(this)

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(32, 32, 32, 32)
        }

        root.addView(TextView(this).apply {
            text = "Dietolog Health Sync"
            textSize = 22f
            gravity = Gravity.CENTER_HORIZONTAL
        })

        serverUrl = edit("Server URL, например https://dietologist.example.com", settings.serverUrl)
        token = edit("Health sync token", settings.token)
        telegramId = edit("Telegram ID", if (settings.telegramId > 0) settings.telegramId.toString() else "")
        telegramId.inputType = InputType.TYPE_CLASS_NUMBER

        root.addView(serverUrl)
        root.addView(token)
        root.addView(telegramId)

        root.addView(button("Сохранить настройки") {
            saveSettings()
            status.text = "Настройки сохранены."
        })

        root.addView(button("Выдать разрешения Health Connect") {
            lifecycleScope.launch {
                if (!health.isAvailable()) {
                    status.text = "Health Connect недоступен. Обнови Android/Google Play Services или установи Health Connect."
                    return@launch
                }
                permissionLauncher.launch(health.permissions)
            }
        })

        root.addView(button("Синхронизировать сейчас") {
            lifecycleScope.launch { syncNow() }
        })

        root.addView(button("Включить автосинхронизацию") {
            saveSettings()
            HealthSyncWorker.schedule(this)
            status.text = "Автосинхронизация включена: примерно раз в 3 часа."
        })

        status = TextView(this).apply {
            text = "Сначала сохрани настройки и выдай разрешения."
            setPadding(0, 24, 0, 0)
        }
        root.addView(status)
        setContentView(root)
    }

    private fun edit(hint: String, value: String): EditText {
        return EditText(this).apply {
            this.hint = hint
            setText(value)
            singleLine = true
        }
    }

    private fun button(text: String, action: () -> Unit): Button {
        return Button(this).apply {
            this.text = text
            setOnClickListener { action() }
        }
    }

    private fun saveSettings() {
        HealthSyncConfig.save(
            this,
            HealthSyncSettings(
                serverUrl = serverUrl.text.toString(),
                token = token.text.toString(),
                telegramId = telegramId.text.toString().toLongOrNull() ?: 0L,
            )
        )
    }

    private suspend fun syncNow() {
        saveSettings()
        status.text = "Синхронизирую..."
        try {
            if (!health.isAvailable()) {
                status.text = "Health Connect недоступен на телефоне."
                return
            }
            val missing = health.missingPermissions()
            if (missing.isNotEmpty()) {
                status.text = "Сначала выдай разрешения Health Connect."
                permissionLauncher.launch(health.permissions)
                return
            }
            val payload = health.readDay()
            withContext(Dispatchers.IO) {
                DietologApiClient().sync(HealthSyncConfig.load(this@MainActivity), payload)
            }
            status.text = "Готово: ${payload.steps} шагов, активные калории ${payload.activeCalories.toInt()}."
        } catch (exc: Exception) {
            status.text = "Ошибка синхронизации: ${exc.message}"
        }
    }
}
