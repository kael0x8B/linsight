package com.linsight.module.aivideo.integration.runtime;

import com.linsight.framework.common.util.json.JsonUtils;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;

import java.util.Map;
import java.util.UUID;

/** Routes preview RPCs through the outbound Edge Agent tunnel. */
@Component
public class RuntimePreviewClient {

    private final RuntimePreviewProperties properties;
    private final NodePreviewTunnelHandler tunnelHandler;

    public RuntimePreviewClient(RuntimePreviewProperties properties, NodePreviewTunnelHandler tunnelHandler) {
        this.properties = properties;
        this.tunnelHandler = tunnelHandler;
    }

    public boolean isEnabled() {
        return properties.isEnabled();
    }

    public boolean isNodeConnected(Long nodeId, Long tenantId) {
        return isEnabled() && tunnelHandler.isConnected(nodeId, tenantId);
    }

    public Session createSession(Long nodeId, Long tenantId, Long cameraId,
                                 String sourceUrl, String streamType) {
        return session(request(nodeId, tenantId, "preview.create", Map.of(
                "cameraId", cameraId,
                "sourceUrl", sourceUrl,
                "streamType", streamType)));
    }

    public Session getSession(Long nodeId, Long tenantId, String sessionId) {
        return session(request(nodeId, tenantId, "preview.get", Map.of("sessionId", sessionId)));
    }

    public Session createWebRtcSession(Long nodeId, Long tenantId, Long cameraId,
                                       String sourceUrl, String offerSdp, String offerType) {
        return session(request(nodeId, tenantId, "webrtc.offer", Map.of(
                "cameraId", cameraId,
                "sourceUrl", sourceUrl,
                "offerSdp", offerSdp,
                "offerType", offerType)));
    }

    public Session getWebRtcSession(Long nodeId, Long tenantId, String sessionId) {
        return session(request(nodeId, tenantId, "webrtc.get", Map.of("sessionId", sessionId)));
    }

    public void releaseWebRtcSession(Long nodeId, Long tenantId, String sessionId) {
        request(nodeId, tenantId, "webrtc.release", Map.of("sessionId", sessionId));
    }

    public Media getMedia(Long nodeId, Long tenantId, String sessionId, String fileName) {
        NodePreviewTunnelHandler.TunnelResult result = request(nodeId, tenantId, "preview.media",
                Map.of("sessionId", sessionId, "fileName", fileName));
        return new Media(result.media(), result.contentType() == null
                ? MediaType.APPLICATION_OCTET_STREAM_VALUE : result.contentType());
    }

    public Map<String, Object> dryRunRule(Long nodeId, Long tenantId, Map<String, Object> payload) {
        return request(nodeId, tenantId, "rule.dry-run", payload).payload();
    }

    public void releaseSession(Long nodeId, Long tenantId, String sessionId) {
        request(nodeId, tenantId, "preview.release", Map.of("sessionId", sessionId));
    }

    private NodePreviewTunnelHandler.TunnelResult request(Long nodeId, Long tenantId,
                                                          String action, Map<String, Object> payload) {
        try {
            return tunnelHandler.request(nodeId, tenantId, action, payload);
        } catch (NodePreviewTunnelHandler.TunnelRequestException exception) {
            throw new RuntimePreviewException(exception);
        }
    }

    private static Session session(NodePreviewTunnelHandler.TunnelResult result) {
        if (result == null || result.payload() == null) {
            return null;
        }
        return JsonUtils.parseObject(JsonUtils.toJsonString(result.payload()), Session.class);
    }

    @Data
    @NoArgsConstructor
    public static class Session {
        private String sessionId;
        private Long cameraId;
        private String protocol;
        private String state;
        private Integer subscriberCount;
        private String diagnosticId;
        private String answerSdp;
        private String answerType;
    }

    @Data
    @AllArgsConstructor
    public static class Media {
        private byte[] body;
        private String contentType;
    }

    public static class RuntimePreviewException extends RuntimeException {
        private final String diagnosticId;

        public RuntimePreviewException(Throwable cause) {
            super("Edge preview request failed", cause);
            this.diagnosticId = cause instanceof NodePreviewTunnelHandler.TunnelRequestException tunnelException
                    ? tunnelException.getDiagnosticId() : UUID.randomUUID().toString();
        }

        public String getDiagnosticId() {
            return diagnosticId;
        }
    }
}
