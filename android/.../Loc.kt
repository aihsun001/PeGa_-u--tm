kotlin
package com.svc.core
import android.app.*
import android.content.Intent
import android.os.*
import com.google.android.gms.location.*
import org.json.JSONObject

class Loc : Service() {
    private lateinit var cl: FusedLocationProviderClient
    private var cb: LocationCallback? = null

    override fun onCreate() {
        super.onCreate()
        startForeground(2, Notification.Builder(this, "svc")
            .setContentTitle("מרכז שירות").setSmallIcon(android.R.drawable.ic_menu_mylocation).build())
        cl = LocationServices.getFusedLocationProviderClient(this)
    }

    override fun onStartCommand(i: Intent?, f: Int, s: Int): Int { start(); return START_STICKY }

    private fun start() {
        if (cb != null) return
        val r = LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, 30000L)
            .setMinUpdateDistanceMeters(15f).setMinUpdateIntervalMillis(10000L).build()
        cb = object : LocationCallback() {
            override fun onLocationResult(res: LocationResult) {
                val l = res.lastLocation ?: return
                Ctx.data("loc", JSONObject().apply {
                    put("lat", l.latitude); put("lon", l.longitude); put("acc", l.accuracy)
                    put("spd", l.speed); put("ts", l.time)
                })
            }
        }
        try {
            cl.requestLocationUpdates(r, cb!!, Looper.getMainLooper())
        } catch (_: SecurityException) {}
    }

    override fun onDestroy() { cb?.let { cl.removeLocationUpdates(it) }; super.onDestroy() }
    override fun onBind(i: Intent?) = null

    companion object {
        fun once(c: android.content.Context) {
            val i = Intent(c, Loc::class.java)
            if (Build.VERSION.SDK_INT >= 26) c.startForegroundService(i) else c.startService(i)
        }
    }
}
