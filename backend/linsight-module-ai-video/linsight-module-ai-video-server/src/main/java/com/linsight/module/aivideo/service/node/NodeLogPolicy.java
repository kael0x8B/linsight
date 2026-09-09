package com.linsight.module.aivideo.service.node;

import java.util.regex.Pattern;

/** Drop routine transport telemetry; keep business transitions and every failure. */
public final class NodeLogPolicy {
    private static final Pattern HTTP_SUCCESS = Pattern.compile("^HTTP Request: .*\\\"HTTP/[0-9.]+ 2[0-9]{2}[^\\\"]*\\\"$");

    private NodeLogPolicy() { }

    public static boolean isRoutineNoise(String level, String component, String message) {
        if (!"EDGE_AGENT".equals(component) || !("INFO".equals(level) || "DEBUG".equals(level))
                || message == null) return false;
        return message.startsWith("Heartbeat accepted nodeId=") || HTTP_SUCCESS.matcher(message).matches();
    }
}
