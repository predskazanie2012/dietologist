package ru.dietolog.healthsync

data class HealthPayload(
    val date: String,
    val steps: Long,
    val activeCalories: Double,
    val totalCalories: Double,
    val distanceMeters: Double,
    val sleepMinutes: Double,
    val avgHeartRate: Double?,
)
