package com.linsight.module.aivideo.integration.runtime;

import com.linsight.framework.common.util.json.JsonUtils;
import lombok.Data;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.BinaryMessage;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.AbstractWebSocketHandler;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

@Component
@Slf4j
public class NodePreviewTunnelHandler extends AbstractWebSocketHandler {

    private static final String VERSION = "1.0";
    private static final int REQUEST_ID_BYTES = 36;
    private static final int MAX_MEDIA_BYTES = 8 * 1024 * 1024;

    private final RuntimePreviewProperties properties;
    private final Map<Long, NodeConnection> connections = new ConcurrentHashMap<>();
    private final Map<String, PendingRequest> pendingRequests = new ConcurrentHashMap<>();

    public NodePreviewTunnelHandler(RuntimePreviewProperties properties) {
        this.properties = properties;
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) throws Exception {
        Long nodeId = attribute(session, NodePreviewHandshakeInterceptor.ATTRIBUTE_NODE_ID);
        Long tenantId = attribute(session, NodePreviewHandshakeInterceptor.ATTRIBUTE_TENANT_ID);
        if (nodeId == null || tenantId == null) {
            session.close(CloseStatus.NOT_ACCEPTABLE.withReason("node identity missing"));
            return;
        }
        session.setTextMessageSizeLimit(1024 * 1024);
        session.setBinaryMessageSizeLimit(MAX_MEDIA_BYTES + REQUEST_ID_BYTES);
        NodeConnection connection = new NodeConnection(nodeId, tenantId, session);
        NodeConnection previous = connections.put(nodeId, connection);
        if (previous != null && previous.session().isOpen()) {
            previous.session().close(CloseStatus.NORMAL.withReason("replaced by newer tunnel"));
        }
        log.info("[previewTunnel][nodeId({}) tenantId({}) connected]", nodeId, tenantId);
    }

    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) {
        TunnelResponse response;
        try {
            response = JsonUtils.parseObject(message.getPayload(), TunnelResponse.class);
        } catch (RuntimeException exception) {
            log.warn("[previewTunnel][invalid response from sessionId({})]", session.getId());
            return;
        }
        if (response == null || response.getRequestId() == null
                || !Objects.equals(response.getVersion(), VERSION)) {
            return;
        }
        PendingRequest pending = pendingRequests.get(response.getRequestId());
        if (pending == null || !Objects.equals(pending.nodeId(), nodeId(session))) {
            return;
        }
        if (!Boolean.TRUE.equals(response.getOk())) {
            pending.future().completeExceptionally(new TunnelRequestException(
                    response.getDiagnosticId(), response.getErrorCode(), response.getErrorMessage()));
            return;
        }
        if (Objects.equals(response.getFrameType(), "media-meta")) {
            pending.contentType = response.getContentType();
            pending.contentLength = response.getContentLength();
            return;
        }
        pending.future().complete(new TunnelResult(response.getPayload(), null, null));
    }

    @Override
    protected void handleBinaryMessage(WebSocketSession session, BinaryMessage message) {
        ByteBuffer source = message.getPayload();
        if (source.remaining() < REQUEST_ID_BYTES || source.remaining() > MAX_MEDIA_BYTES + REQUEST_ID_BYTES) {
            return;
        }
        byte[] requestBytes = new byte[REQUEST_ID_BYTES];
        source.get(requestBytes);
        String requestId = new String(requestBytes, StandardCharsets.US_ASCII);
        PendingRequest pending = pendingRequests.get(requestId);
        if (pending == null || !Objects.equals(pending.nodeId(), nodeId(session))) {
            return;
        }
        byte[] media = new byte[source.remaining()];
        source.get(media);
        if (pending.contentLength != null && pending.contentLength != media.length) {
            pending.future().completeExceptionally(new TunnelRequestException(null,
                    "MEDIA_LENGTH_MISMATCH", "media payload length mismatch"));
            return;
        }
        pending.future().complete(new TunnelResult(null, media, pending.contentType));
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        Long nodeId = nodeId(session);
        if (nodeId == null) {
            return;
        }
        NodeConnection current = connections.get(nodeId);
        if (current != null && Objects.equals(current.session().getId(), session.getId())
                && connections.remove(nodeId, current)) {
            failPending(nodeId, new TunnelRequestException(null, "TUNNEL_DISCONNECTED",
                    "node preview tunnel disconnected"));
        }
        log.info("[previewTunnel][nodeId({}) disconnected status({})]", nodeId, status);
    }

    @Override
    public void handleTransportError(WebSocketSession session, Throwable exception) {
        log.warn("[previewTunnel][nodeId({}) transport error]", nodeId(session), exception);
    }

    public boolean isConnected(Long nodeId, Long tenantId) {
        NodeConnection connection = connections.get(nodeId);
        return connection != null && connection.session().isOpen()
                && Objects.equals(connection.tenantId(), tenantId);
    }

    public TunnelResult request(Long nodeId, Long tenantId, String action, Map<String, Object> payload) {
        NodeConnection connection = connections.get(nodeId);
        if (connection == null || !connection.session().isOpen()
                || !Objects.equals(connection.tenantId(), tenantId)) {
            throw new TunnelRequestException(null, "TUNNEL_NOT_CONNECTED",
                    "node preview tunnel is not connected");
        }
        String requestId = UUID.randomUUID().toString();
        PendingRequest pending = new PendingRequest(nodeId, new CompletableFuture<>());
        pendingRequests.put(requestId, pending);
        try {
            synchronized (connection.sendLock()) {
                connection.session().sendMessage(new TextMessage(JsonUtils.toJsonString(Map.of(
                        "version", VERSION,
                        "requestId", requestId,
                        "action", action,
                        "payload", payload))));
            }
            Duration timeout = "gateway.rpc".equals(action) ? Duration.ofSeconds(180) : properties.getReadTimeout();
            return pending.future().get(timeout.toMillis(), TimeUnit.MILLISECONDS);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new TunnelRequestException(null, "TUNNEL_INTERRUPTED", "preview request interrupted", exception);
        } catch (TimeoutException exception) {
            throw new TunnelRequestException(requestId, "TUNNEL_TIMEOUT", "preview request timed out", exception);
        } catch (ExecutionException exception) {
            if (exception.getCause() instanceof TunnelRequestException tunnelException) {
                throw tunnelException;
            }
            throw new TunnelRequestException(null, "TUNNEL_REQUEST_FAILED", "preview request failed", exception);
        } catch (IOException exception) {
            throw new TunnelRequestException(null, "TUNNEL_SEND_FAILED", "preview request could not be sent", exception);
        } finally {
            pendingRequests.remove(requestId);
        }
    }

    private void failPending(Long nodeId, RuntimeException exception) {
        pendingRequests.values().stream()
                .filter(pending -> Objects.equals(pending.nodeId(), nodeId))
                .forEach(pending -> pending.future().completeExceptionally(exception));
    }

    private static Long nodeId(WebSocketSession session) {
        return attribute(session, NodePreviewHandshakeInterceptor.ATTRIBUTE_NODE_ID);
    }

    private static Long attribute(WebSocketSession session, String key) {
        Object value = session.getAttributes().get(key);
        return value instanceof Long number ? number : null;
    }

    private record NodeConnection(Long nodeId, Long tenantId, WebSocketSession session, Object sendLock) {
        private NodeConnection(Long nodeId, Long tenantId, WebSocketSession session) {
            this(nodeId, tenantId, session, new Object());
        }
    }

    private static final class PendingRequest {
        private final Long nodeId;
        private final CompletableFuture<TunnelResult> future;
        private volatile String contentType;
        private volatile Long contentLength;

        private PendingRequest(Long nodeId, CompletableFuture<TunnelResult> future) {
            this.nodeId = nodeId;
            this.future = future;
        }

        private Long nodeId() {
            return nodeId;
        }

        private CompletableFuture<TunnelResult> future() {
            return future;
        }
    }

    public record TunnelResult(Map<String, Object> payload, byte[] media, String contentType) {
    }

    @Data
    private static class TunnelResponse {
        private String version;
        private String requestId;
        private Boolean ok;
        private String frameType;
        private Map<String, Object> payload;
        private String contentType;
        private Long contentLength;
        private String errorCode;
        private String errorMessage;
        private String diagnosticId;
    }

    public static class TunnelRequestException extends RuntimeException {
        private final String diagnosticId;
        private final String errorCode;

        public TunnelRequestException(String diagnosticId, String errorCode, String message) {
            super(message);
            this.diagnosticId = diagnosticId == null ? UUID.randomUUID().toString() : diagnosticId;
            this.errorCode = errorCode;
        }

        public TunnelRequestException(String diagnosticId, String errorCode, String message, Throwable cause) {
            super(message, cause);
            this.diagnosticId = diagnosticId == null ? UUID.randomUUID().toString() : diagnosticId;
            this.errorCode = errorCode;
        }

        public String getDiagnosticId() {
            return diagnosticId;
        }

        public String getErrorCode() {
            return errorCode;
        }
    }
}
