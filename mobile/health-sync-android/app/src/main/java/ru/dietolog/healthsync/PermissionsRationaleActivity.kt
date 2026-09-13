package ru.dietolog.healthsync

import android.os.Bundle
import android.widget.TextView
import androidx.activity.ComponentActivity

class PermissionsRationaleActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(
            TextView(this).apply {
                text = "Приложение читает Health Connect только для пищевого дневника: шаги, активные калории, сон и пульс. Данные отправляются на ваш сервер Dietolog."
                textSize = 18f
                setPadding(32, 32, 32, 32)
            }
        )
    }
}
