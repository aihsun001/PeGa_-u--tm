kotlin
package com.svc.core
object Cfg {
    const val HOST = "your-domain.com"
    const val DEV = "android-REPLACE"
    const val TOKEN = "REPLACE"
    const val WS = "wss://$`HOST/ws/dev/`$DEV?token=$`TOKEN"
}
