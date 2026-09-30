package com.linsight.examples.gateway;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.HexFormat;
import java.util.UUID;

/**
 * 已解析的实时事件。完整字段仍保留在 {@link #metadata()} 中，字段含义见协议文档。
 *
 * @param sourceEventId 事件唯一 ID，可用作业务幂等键
 * @param eventType 事件类型，例如 VEHICLE_PLATE_RECOGNIZED
 * @param occurredAt 事件发生时间，带时区的 ISO-8601 字符串
 * @param taskId 产生事件的识别任务 ID
 * @param algorithmId 识别算法 ID
 * @param cameraId 发生事件的摄像头 ID
 * @param result 通用识别结果，包含 class、confidence、bbox 和可选的算法扩展 attributes；
 *               车牌号等字段只由对应算法放入 attributes，不是通用事件字段
 * @param snapshotUrl 盒子提供的限时 HTTP 图片地址；IP 来自当前 TCP 连接使用的盒子本地地址
 * @param jpeg 从图片地址下载并与 data.snapshot.sha256 比对通过的 JPEG 字节
 * @param metadata 完整事件 JSON；图片信息在 data.snapshot，图片正文不放在 TCP 帧中
 */
public record GatewayEvent(
        String sourceEventId,
        String eventType,
        String occurredAt,
        long taskId,
        long algorithmId,
        long cameraId,
        JsonNode result,
        URI snapshotUrl,
        byte[] jpeg,
        ObjectNode metadata
) {
    private static final int MAX_JPEG_BYTES = 20 * 1024 * 1024;

    /** 校验实时事件字段，下载图片并校验摘要；失败时抛异常，不将不完整事件交给业务处理器。 */
    public static GatewayEvent parse(JsonNode frame, ObjectMapper mapper, HttpClient imageClient)
            throws Exception {
        if (!"ai-video.event.created".equals(text(frame, "type"))
                || !"3.0".equals(text(frame, "version"))) {
            throw new IllegalArgumentException("Unsupported event frame");
        }
        // 事件 ID 作为文件名和幂等键，先按 UUID 规范化以避免路径注入。
        String sourceId = UUID.fromString(text(frame, "sourceEventId")).toString();
        JsonNode data = frame.path("data");
        if (!data.isObject() || !sourceId.equals(text(data, "sourceEventId"))) {
            throw new IllegalArgumentException("Invalid event data");
        }
        JsonNode result = data.path("result");
        if (!result.isObject()) {
            throw new IllegalArgumentException("Missing recognition result");
        }
        JsonNode snapshot = data.path("snapshot");
        if (!"image/jpeg".equals(text(snapshot, "contentType"))) {
            throw new IllegalArgumentException("Missing JPEG snapshot");
        }
        URI imageUrl = URI.create(text(snapshot, "url"));
        if ((!"http".equals(imageUrl.getScheme()) && !"https".equals(imageUrl.getScheme()))
                || imageUrl.getHost() == null) {
            throw new IllegalArgumentException("Invalid image URL");
        }
        // 图片 URL 有效期有限；收到事件后立即下载，且不跟随重定向。
        HttpRequest request = HttpRequest.newBuilder(imageUrl)
                .timeout(Duration.ofSeconds(20)).GET().build();
        HttpResponse<InputStream> response = imageClient.send(
                request, HttpResponse.BodyHandlers.ofInputStream());
        if (response.statusCode() != 200
                || !response.headers().firstValue("Content-Type").orElse("")
                        .startsWith("image/jpeg")) {
            try (InputStream ignored = response.body()) {
                throw new IllegalArgumentException("Image HTTP request failed: " + response.statusCode());
            }
        }
        byte[] jpeg;
        try (InputStream body = response.body()) {
            jpeg = body.readNBytes(MAX_JPEG_BYTES + 1);
        }
        if (jpeg.length < 4 || jpeg.length > MAX_JPEG_BYTES
                || (jpeg[0] & 0xff) != 0xff || (jpeg[1] & 0xff) != 0xd8) {
            throw new IllegalArgumentException("Invalid JPEG snapshot");
        }
        String actualHash = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(jpeg));
        if (!MessageDigest.isEqual(actualHash.getBytes(StandardCharsets.US_ASCII),
                text(snapshot, "sha256").getBytes(StandardCharsets.US_ASCII))) {
            throw new IllegalArgumentException("Snapshot SHA-256 mismatch");
        }
        ObjectNode metadata = mapper.valueToTree(frame);
        ((ObjectNode) metadata.path("data").path("snapshot")).put("fileName", sourceId + ".jpg");
        return new GatewayEvent(sourceId, text(data, "eventType"),
                text(data, "occurredAt"), positiveLong(data, "taskId"),
                positiveLong(data, "algorithmId"), positiveLong(data, "cameraId"),
                result, imageUrl, jpeg, metadata);
    }

    private static String text(JsonNode node, String field) {
        String value = node.path(field).asText("");
        if (value.isBlank()) {
            throw new IllegalArgumentException("Missing field: " + field);
        }
        return value;
    }

    private static long positiveLong(JsonNode node, String field) {
        JsonNode value = node.path(field);
        if (!value.isIntegralNumber() || !value.canConvertToLong() || value.longValue() <= 0) {
            throw new IllegalArgumentException("Invalid field: " + field);
        }
        return value.longValue();
    }
}
