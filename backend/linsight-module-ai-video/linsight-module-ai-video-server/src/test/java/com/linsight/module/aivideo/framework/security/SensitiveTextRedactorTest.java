package com.linsight.module.aivideo.framework.security;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SensitiveTextRedactorTest {
    @Test
    void textAndNestedContextMustNotRetainCredentialsOrRtspPaths() {
        String text = SensitiveTextRedactor.redactText(
                "open rtsp://admin:camera-pass@10.0.0.8/live/main password=plain-secret");
        String context = SensitiveTextRedactor.redactContext("""
                {"runtime_api_key":"runtime-secret","nested":{"token":"token-secret"},
                 "url":"https://user:pass@example.invalid/path"}
                """);

        assertFalse(text.contains("camera-pass"));
        assertFalse(text.contains("plain-secret"));
        assertTrue(text.contains("[REDACTED_RTSP_URL]"));
        assertFalse(context.contains("runtime-secret"));
        assertFalse(context.contains("token-secret"));
        assertFalse(context.contains("user:pass"));
        assertTrue(context.contains("***"));
    }
}
