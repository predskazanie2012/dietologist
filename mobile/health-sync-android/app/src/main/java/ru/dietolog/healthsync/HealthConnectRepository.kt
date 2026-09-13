package ru.dietolog.healthsync

import android.content.Context
import androidx.health.connect.client.HealthConnectClient
import androidx.health.connect.client.permission.HealthPermission
import androidx.health.connect.client.records.ActiveCaloriesBurnedRecord
import androidx.health.connect.client.records.DistanceRecord
import androidx.health.connect.client.records.HeartRateRecord
import androidx.health.connect.client.records.SleepSessionRecord
import androidx.health.connect.client.records.StepsRecord
import androidx.health.connect.client.records.TotalCaloriesBurnedRecord
import androidx.health.connect.client.request.AggregateRequest
import androidx.health.connect.client.request.ReadRecordsRequest
import androidx.health.connect.client.time.TimeRangeFilter
import androidx.health.connect.client.permission.HealthPermission.Companion.PERMISSION_READ_HEALTH_DATA_IN_BACKGROUND
import java.time.Duration
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

class HealthConnectRepository(private val context: Context) {
    val permissions: Set<String> = setOf(
        HealthPermission.getReadPermission(StepsRecord::class),
        HealthPermission.getReadPermission(ActiveCaloriesBurnedRecord::class),
        HealthPermission.getReadPermission(TotalCaloriesBurnedRecord::class),
        HealthPermission.getReadPermission(DistanceRecord::class),
        HealthPermission.getReadPermission(SleepSessionRecord::class),
        HealthPermission.getReadPermission(HeartRateRecord::class),
        PERMISSION_READ_HEALTH_DATA_IN_BACKGROUND,
    )

    private val client: HealthConnectClient by lazy {
        HealthConnectClient.getOrCreate(context)
    }

    fun isAvailable(): Boolean {
        return HealthConnectClient.getSdkStatus(context) == HealthConnectClient.SDK_AVAILABLE
    }

    suspend fun missingPermissions(): Set<String> {
        val granted = client.permissionController.getGrantedPermissions()
        return permissions - granted
    }

    suspend fun readDay(day: LocalDate = LocalDate.now()): HealthPayload {
        val zone = ZoneId.systemDefault()
        val start = day.atStartOfDay(zone).toInstant()
        val end = day.plusDays(1).atStartOfDay(zone).toInstant().coerceAtMost(Instant.now())

        val aggregate = client.aggregate(
            AggregateRequest(
                metrics = setOf(
                    StepsRecord.COUNT_TOTAL,
                    ActiveCaloriesBurnedRecord.ACTIVE_CALORIES_TOTAL,
                    TotalCaloriesBurnedRecord.ENERGY_TOTAL,
                    DistanceRecord.DISTANCE_TOTAL,
                ),
                timeRangeFilter = TimeRangeFilter.between(start, end),
            )
        )

        val sleepMinutes = readSleepMinutes(start, end)
        val avgHeartRate = readAvgHeartRate(start, end)

        return HealthPayload(
            date = day.toString(),
            steps = aggregate[StepsRecord.COUNT_TOTAL] ?: 0L,
            activeCalories = aggregate[ActiveCaloriesBurnedRecord.ACTIVE_CALORIES_TOTAL]?.inKilocalories ?: 0.0,
            totalCalories = aggregate[TotalCaloriesBurnedRecord.ENERGY_TOTAL]?.inKilocalories ?: 0.0,
            distanceMeters = aggregate[DistanceRecord.DISTANCE_TOTAL]?.inMeters ?: 0.0,
            sleepMinutes = sleepMinutes,
            avgHeartRate = avgHeartRate,
        )
    }

    private suspend fun readSleepMinutes(start: Instant, end: Instant): Double {
        val response = client.readRecords(
            ReadRecordsRequest(
                recordType = SleepSessionRecord::class,
                timeRangeFilter = TimeRangeFilter.between(start, end),
            )
        )
        return response.records.sumOf {
            Duration.between(it.startTime, it.endTime).toMinutes().coerceAtLeast(0).toDouble()
        }
    }

    private suspend fun readAvgHeartRate(start: Instant, end: Instant): Double? {
        val response = client.readRecords(
            ReadRecordsRequest(
                recordType = HeartRateRecord::class,
                timeRangeFilter = TimeRangeFilter.between(start, end),
            )
        )
        val samples = response.records.flatMap { it.samples }
        if (samples.isEmpty()) return null
        return samples.map { it.beatsPerMinute.toDouble() }.average()
    }
}

private fun Instant.coerceAtMost(maximum: Instant): Instant {
    return if (this.isAfter(maximum)) maximum else this
}
