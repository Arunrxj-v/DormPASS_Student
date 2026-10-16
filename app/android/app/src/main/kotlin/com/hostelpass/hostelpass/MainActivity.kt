package com.hostelpass.hostelpass

import android.content.Intent
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private var channel: MethodChannel? = null
    private var pendingLink: String? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        channel = MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger,
            "hostelpass/deep_links",
        )
        channel?.setMethodCallHandler { call, result ->
            if (call.method == "getInitialLink") {
                result.success(pendingLink)
                pendingLink = null
            } else {
                result.notImplemented()
            }
        }
        // Cold start: the VIEW intent's URI exists before Dart is running.
        // Capture it here; the Dart side collects it once via getInitialLink.
        // (The Flutter engine only auto-delivers http(s) app links, so
        // custom-scheme links must be forwarded by hand.)
        intent?.data?.toString()?.let { if (pendingLink == null) pendingLink = it }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        // singleTop reuse while the app is already running: push straight
        // through if the Dart side is up, otherwise park it for getInitialLink.
        val link = intent.data?.toString()
        if (link != null) {
            if (channel != null) {
                channel?.invokeMethod("onLink", link)
            } else {
                pendingLink = link
            }
        }
    }
}
