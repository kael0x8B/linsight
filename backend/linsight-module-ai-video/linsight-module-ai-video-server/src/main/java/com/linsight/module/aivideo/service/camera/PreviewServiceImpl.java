package com.linsight.module.aivideo.service.camera;

import com.linsight.module.aivideo.controller.admin.camera.vo.PreviewSessionRespVO;
import com.linsight.module.aivideo.controller.node.camera.vo.NodeOverlayReportReqVO;
import com.linsight.module.aivideo.integration.runtime.RuntimePreviewClient;
import com.linsight.module.aivideo.service.node.NodeService;
import com.linsight.module.aivideo.service.task.TaskService;
import com.linsight.module.infra.api.websocket.WebSocketSenderApi;
import com.linsight.framework.common.enums.UserTypeEnum;
import com.linsight.framework.tenant.core.context.TenantContextHolder;
import jakarta.annotation.Resource;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;
import java.util.function.LongSupplier;

import static com.linsight.framework.common.exception.util.ServiceExceptionUtil.exception;
import static com.linsight.module.aivideo.enums.camera.ErrorCodeConstants.*;

@Service
@Slf4j
public class PreviewServiceImpl implements PreviewService {

    public static final String OVERLAY_MESSAGE_TYPE = "ai-video-preview-overlay";
    private static final String HLS_SEGMENT_PATTERN = "segment-\\d{6}\\.ts";
    private static final long SESSION_LEASE_NANOS = TimeUnit.SECONDS.toNanos(90);

    @Resource
    private CameraService cameraService;
    @Resource
    private RuntimePreviewClient runtimePreviewClient;
    @Resource
    private NodeService nodeService;
    @Resource
    private TaskService taskService;
    @Resource
    private WebSocketSenderApi webSocketSenderApi;

    private final Map<String, SessionOwner> sessionOwners = new ConcurrentHashMap<>();
    private LongSupplier monotonicNanos = System::nanoTime;

    @Override
    public PreviewSessionRespVO createPreview(Long cameraId, Long nodeId, String streamType,
                                              Long tenantId, Long userId) {
        if (!runtimePreviewClient.isEnabled()) {
            throw exception(CAMERA_PREVIEW_RUNTIME_DISABLED);
        }
        nodeService.validateNodeAvailable(nodeId);
        if (!runtimePreviewClient.isNodeConnected(nodeId, tenantId)) {
            throw exception(CAMERA_PREVIEW_TUNNEL_NOT_CONNECTED, nodeId, UUID.randomUUID());
        }
        String selectedStream = activeOrRequestedStream(cameraId, nodeId, streamType);
        String sourceUrl = cameraService.getRuntimeStreamUrl(cameraId, selectedStream);
        try {
            RuntimePreviewClient.Session runtimeSession = runtimePreviewClient.createSession(
                    nodeId, tenantId, cameraId, sourceUrl, selectedStream);
            if (runtimeSession == null || runtimeSession.getSessionId() == null) {
                throw new RuntimePreviewClient.RuntimePreviewException(
                        new IllegalStateException("Runtime preview response is empty"));
            }
            discardExpiredSessions();
            sessionOwners.put(runtimeSession.getSessionId(),
                    new SessionOwner(tenantId, userId, cameraId, nodeId, "HLS", monotonicNanos.getAsLong()));
            return convert(runtimeSession, nodeId);
        } catch (RuntimePreviewClient.RuntimePreviewException exception) {
            RuntimeException serviceException = exception(CAMERA_PREVIEW_UNAVAILABLE, exception.getDiagnosticId());
            serviceException.initCause(exception);
            throw serviceException;
        }
    }

    @Override
    public PreviewSessionRespVO createWebRtcPreview(Long cameraId, Long nodeId, String offerSdp,
                                                    String offerType, Long tenantId, Long userId) {
        if (!runtimePreviewClient.isEnabled()) {
            throw exception(CAMERA_PREVIEW_RUNTIME_DISABLED);
        }
        nodeService.validateNodeAvailable(nodeId);
        if (!runtimePreviewClient.isNodeConnected(nodeId, tenantId)) {
            throw exception(CAMERA_PREVIEW_TUNNEL_NOT_CONNECTED, nodeId, UUID.randomUUID());
        }
        String sourceUrl = cameraService.getRuntimeStreamUrl(cameraId,
                activeOrRequestedStream(cameraId, nodeId, "SUB"));
        try {
            RuntimePreviewClient.Session runtimeSession = runtimePreviewClient.createWebRtcSession(
                    nodeId, tenantId, cameraId, sourceUrl, offerSdp, offerType);
            if (runtimeSession == null || runtimeSession.getSessionId() == null
                    || runtimeSession.getAnswerSdp() == null) {
                throw new RuntimePreviewClient.RuntimePreviewException(
                        new IllegalStateException("Runtime WebRTC response is empty"));
            }
            discardExpiredSessions();
            sessionOwners.put(runtimeSession.getSessionId(),
                    new SessionOwner(tenantId, userId, cameraId, nodeId, "WEBRTC", monotonicNanos.getAsLong()));
            return convert(runtimeSession, nodeId);
        } catch (RuntimePreviewClient.RuntimePreviewException exception) {
            RuntimeException serviceException = exception(CAMERA_PREVIEW_UNAVAILABLE, exception.getDiagnosticId());
            serviceException.initCause(exception);
            throw serviceException;
        }
    }

    private String activeOrRequestedStream(Long cameraId, Long nodeId, String requestedStream) {
        String active = taskService.getActiveStreamType(cameraId, nodeId);
        if (active != null) return active;
        return "MAIN".equals(requestedStream) ? "MAIN" : "SUB";
    }

    @Override
    public PreviewSessionRespVO getPreview(String sessionId, Long tenantId, Long userId) {
        validateOwner(sessionId, tenantId, userId);
        try {
            SessionOwner owner = sessionOwners.get(sessionId);
            RuntimePreviewClient.Session runtimeSession = Objects.equals(owner.protocol(), "WEBRTC")
                    ? runtimePreviewClient.getWebRtcSession(owner.nodeId(), tenantId, sessionId)
                    : runtimePreviewClient.getSession(owner.nodeId(), tenantId, sessionId);
            if (runtimeSession == null) {
                throw exception(CAMERA_PREVIEW_SESSION_NOT_FOUND);
            }
            return convert(runtimeSession, owner.nodeId());
        } catch (RuntimePreviewClient.RuntimePreviewException exception) {
            sessionOwners.remove(sessionId);
            RuntimeException serviceException = exception(CAMERA_PREVIEW_SESSION_NOT_FOUND);
            serviceException.initCause(exception);
            throw serviceException;
        }
    }

    @Override
    public PreviewMedia getMedia(String sessionId, String fileName, Long tenantId, Long userId) {
        validateOwner(sessionId, tenantId, userId);
        SessionOwner owner = sessionOwners.get(sessionId);
        if (!Objects.equals(owner.protocol(), "HLS")) {
            throw exception(CAMERA_PREVIEW_MEDIA_NOT_READY);
        }
        if (!Objects.equals(fileName, "index.m3u8") && !fileName.matches(HLS_SEGMENT_PATTERN)) {
            throw exception(CAMERA_PREVIEW_MEDIA_NOT_READY);
        }
        try {
            RuntimePreviewClient.Media media = runtimePreviewClient.getMedia(
                    owner.nodeId(), tenantId, sessionId, fileName);
            if (media == null || media.getBody() == null) {
                throw exception(CAMERA_PREVIEW_MEDIA_NOT_READY);
            }
            return new PreviewMedia(media.getBody(), media.getContentType());
        } catch (RuntimePreviewClient.RuntimePreviewException exception) {
            throw exception(CAMERA_PREVIEW_MEDIA_NOT_READY);
        }
    }

    @Override
    public void releasePreview(String sessionId, Long tenantId, Long userId) {
        validateOwner(sessionId, tenantId, userId);
        SessionOwner owner = sessionOwners.remove(sessionId);
        try {
            if (Objects.equals(owner.protocol(), "WEBRTC")) {
                runtimePreviewClient.releaseWebRtcSession(owner.nodeId(), tenantId, sessionId);
            } else {
                runtimePreviewClient.releaseSession(owner.nodeId(), tenantId, sessionId);
            }
        } catch (RuntimePreviewClient.RuntimePreviewException exception) {
            // Runtime 可能已经按空闲超时释放；控制面的释放操作仍保持幂等。
            log.debug("[releasePreview][sessionId({}) Runtime 会话已不存在]", sessionId, exception);
        }
    }

    @Override
    public void publishOverlay(NodeOverlayReportReqVO reqVO, Long nodeId) {
        Long tenantId = TenantContextHolder.getRequiredTenantId();
        // Browser reload/close cannot reliably finish its release request. Expire
        // abandoned recipients so reconnects do not multiply each JPEG push forever.
        discardExpiredSessions();
        List<Map.Entry<String, SessionOwner>> recipients = sessionOwners.entrySet().stream()
                .filter(entry -> Objects.equals(entry.getValue().tenantId(), tenantId))
                .filter(entry -> Objects.equals(entry.getValue().cameraId(), reqVO.getCameraId()))
                .toList();
        if (recipients.isEmpty()) {
            return;
        }
        taskService.validateRuntimeOverlay(nodeId, reqVO.getTaskId(), reqVO.getRunId(), reqVO.getCameraId());
        for (Map.Entry<String, SessionOwner> recipient : recipients) {
            Map<String, Object> data = new LinkedHashMap<>();
            data.put("sessionId", recipient.getKey());
            data.put("cameraId", reqVO.getCameraId());
            data.put("nodeId", nodeId);
            data.put("frameKey", reqVO.getFrameKey());
            data.put("taskId", reqVO.getTaskId());
            data.put("runId", reqVO.getRunId());
            data.put("frameId", reqVO.getFrameId());
            data.put("timestamp", reqVO.getTimestamp());
            data.put("sourceWidth", reqVO.getSourceWidth());
            data.put("sourceHeight", reqVO.getSourceHeight());
            data.put("objects", reqVO.getObjects());
            data.put("imageBase64", reqVO.getImageBase64());
            data.put("streamId", reqVO.getStreamId());
            data.put("sourcePts", reqVO.getSourcePts());

            Map<String, Object> envelope = new LinkedHashMap<>();
            envelope.put("type", "preview.overlay.frame");
            envelope.put("version", "1.0");
            envelope.put("messageId", UUID.randomUUID().toString());
            envelope.put("occurredAt", Instant.now());
            envelope.put("data", data);
            try {
                webSocketSenderApi.sendObject(UserTypeEnum.ADMIN.getValue(),
                        recipient.getValue().userId(), OVERLAY_MESSAGE_TYPE, envelope);
            } catch (RuntimeException error) {
                // Overlay 是可丢弃的实时数据；单个离线浏览器不能阻塞其他会话或边缘任务。
                log.debug("[publishOverlay][sessionId({}) WebSocket 投递已跳过]", recipient.getKey(), error);
            }
        }
    }

    private void validateOwner(String sessionId, Long tenantId, Long userId) {
        SessionOwner owner = sessionOwners.get(sessionId);
        long now = monotonicNanos.getAsLong();
        if (owner == null || now - owner.lastAccessNanos() > SESSION_LEASE_NANOS) {
            if (owner != null) sessionOwners.remove(sessionId, owner);
            throw exception(CAMERA_PREVIEW_SESSION_NOT_FOUND);
        }
        if (!Objects.equals(owner.tenantId(), tenantId) || !Objects.equals(owner.userId(), userId)) {
            throw exception(CAMERA_PREVIEW_SESSION_FORBIDDEN);
        }
        sessionOwners.replace(sessionId, owner, new SessionOwner(owner.tenantId(), owner.userId(),
                owner.cameraId(), owner.nodeId(), owner.protocol(), now));
    }

    private void discardExpiredSessions() {
        long now = monotonicNanos.getAsLong();
        sessionOwners.entrySet().removeIf(entry -> now - entry.getValue().lastAccessNanos() > SESSION_LEASE_NANOS);
    }

    private static PreviewSessionRespVO convert(RuntimePreviewClient.Session session, Long nodeId) {
        PreviewSessionRespVO respVO = new PreviewSessionRespVO();
        respVO.setSessionId(session.getSessionId());
        respVO.setCameraId(session.getCameraId());
        respVO.setNodeId(nodeId);
        respVO.setProtocol(session.getProtocol());
        respVO.setState(session.getState());
        respVO.setSubscriberCount(session.getSubscriberCount());
        respVO.setDiagnosticId(session.getDiagnosticId());
        if (Objects.equals(session.getProtocol(), "HLS")) {
            respVO.setManifestUrl("/admin-api/ai-video/camera/preview/media/"
                    + session.getSessionId() + "/index.m3u8");
        }
        respVO.setAnswerSdp(session.getAnswerSdp());
        respVO.setAnswerType(session.getAnswerType());
        respVO.setOverlayMessageType(OVERLAY_MESSAGE_TYPE);
        return respVO;
    }

    private record SessionOwner(Long tenantId, Long userId, Long cameraId, Long nodeId,
                                String protocol, long lastAccessNanos) {
    }

}
