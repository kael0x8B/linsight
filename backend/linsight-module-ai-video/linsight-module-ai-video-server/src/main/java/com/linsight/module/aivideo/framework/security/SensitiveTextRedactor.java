package com.linsight.module.aivideo.framework.security;

import com.linsight.framework.common.util.json.JsonUtils;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

public final class SensitiveTextRedactor {
    private static final Pattern RTSP_URL = Pattern.compile("(?i)rtsp[s]?://\\S+");
    private static final Pattern URL_USER_INFO = Pattern.compile("(?i)(https?://)[^/@\\s]+@");
    private static final Pattern KEY_VALUE_SECRET = Pattern.compile(
            "(?i)(password|passwd|token|secret|credential|authorization|api[-_]?key)"
                    + "(\\s*[=:]\\s*)([^\\s,;]+)");
    private static final Set<String> SENSITIVE_KEYS = Set.of(
            "password", "passwd", "token", "secret", "credential", "authorization",
            "apikey", "runtimeapikey", "streamurl",
            "sourceurl", "rtspurl");

    private SensitiveTextRedactor() {
    }

    public static String redactText(String value) {
        if (value == null) {
            return null;
        }
        String result = RTSP_URL.matcher(value).replaceAll("[REDACTED_RTSP_URL]");
        result = URL_USER_INFO.matcher(result).replaceAll("$1***@");
        return KEY_VALUE_SECRET.matcher(result).replaceAll("$1$2***");
    }

    public static String redactContext(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        Map<String, Object> parsed = JsonUtils.parseMap(value);
        if (parsed == null) {
            return JsonUtils.toJsonString(Map.of("invalidContext", true));
        }
        return JsonUtils.toJsonString(redactMap(parsed));
    }

    private static Map<String, Object> redactMap(Map<?, ?> source) {
        Map<String, Object> result = new LinkedHashMap<>();
        source.forEach((key, item) -> {
            String name = String.valueOf(key);
            result.put(name, sensitiveKey(name) ? "***" : redactValue(item));
        });
        return result;
    }

    private static Object redactValue(Object value) {
        if (value instanceof Map<?, ?> map) {
            return redactMap(map);
        }
        if (value instanceof List<?> list) {
            List<Object> result = new ArrayList<>(list.size());
            list.forEach(item -> result.add(redactValue(item)));
            return result;
        }
        return value instanceof String text ? redactText(text) : value;
    }

    private static boolean sensitiveKey(String key) {
        return SENSITIVE_KEYS.contains(key.replace("-", "").replace("_", "")
                .toLowerCase(Locale.ROOT));
    }
}
