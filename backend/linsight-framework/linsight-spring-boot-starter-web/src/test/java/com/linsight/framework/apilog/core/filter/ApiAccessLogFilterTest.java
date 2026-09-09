package com.linsight.framework.apilog.core.filter;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ApiAccessLogFilterTest {

    @Test
    void shouldSanitizeDefaultAndEndpointSpecificKeys() {
        String sanitized = ApiAccessLogFilter.sanitizeJson("""
                {
                  "code": "NODE-1",
                  "password": "camera-password",
                  "bootstrapToken": "one-time-token",
                  "mainStreamUri": "/Streaming/Channels/101"
                }
                """, new String[]{"bootstrapToken", "mainStreamUri"});

        assertTrue(sanitized.contains("NODE-1"));
        assertFalse(sanitized.contains("camera-password"));
        assertFalse(sanitized.contains("one-time-token"));
        assertFalse(sanitized.contains("/Streaming/Channels/101"));
    }

}
