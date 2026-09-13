package ru.dietolog.healthsync

import android.content.Context
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import java.util.concurrent.TimeUnit

class HealthSyncWorker(
    appContext: Context,
    params: WorkerParameters,
) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): Result {
        return try {
            val settings = HealthSyncConfig.load(applicationContext)
            val health = HealthConnectRepository(applicationContext)
            if (!health.isAvailable() || health.missingPermissions().isNotEmpty()) {
                return Result.retry()
            }
            val payload = health.readDay()
            DietologApiClient().sync(settings, payload)
            Result.success()
        } catch (_: Exception) {
            Result.retry()
        }
    }

    companion object {
        private const val WORK_NAME = "dietolog_health_sync"

        fun schedule(context: Context) {
            val request = PeriodicWorkRequestBuilder<HealthSyncWorker>(3, TimeUnit.HOURS)
                .build()
            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                WORK_NAME,
                ExistingPeriodicWorkPolicy.UPDATE,
                request,
            )
        }
    }
}
