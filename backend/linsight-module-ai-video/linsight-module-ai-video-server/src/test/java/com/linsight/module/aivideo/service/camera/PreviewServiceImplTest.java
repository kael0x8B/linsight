package com.linsight.module.aivideo.service.camera;

import com.linsight.framework.common.exception.ServiceException;
import com.linsight.framework.tenant.core.context.TenantContextHolder;
import com.linsight.module.aivideo.controller.admin.camera.vo.PreviewSessionRespVO;
import com.linsight.module.aivideo.controller.node.camera.vo.NodeOverlayReportReqVO;
import com.linsight.module.aivideo.integration.runtime.RuntimePreviewClient;
import com.linsight.module.aivideo.service.node.NodeService;
import com.linsight.module.aivideo.service.task.TaskService;
import com.linsight.module.infra.api.websocket.WebSocketSenderApi;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.test.util.ReflectionTestUtils;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.LongSupplier;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class PreviewServiceImplTest {

    @Mock
    private CameraService cameraService;
    @Mock
    private RuntimePreviewClient runtimePreviewClient;
    @Mock
    private NodeService nodeService;
    @Mock
    private TaskService taskService;
    @Mock
    private WebSocketSenderApi webSocketSenderApi;
    @InjectMocks
    private PreviewServiceImpl previewService;

    @BeforeEach
    void setTenant() {
        TenantContextHolder.setTenantId(1L);
        lenient().when(runtimePreviewClient.isNodeConnected(3L, 1L)).thenReturn(true);
    }

    @AfterEach
    void clearTenant() {
        TenantContextHolder.clear();
    }

    @Test
    void createPreviewMustKeepSourceSecretInsideRuntimeBoundary() {
        when(runtimePreviewClient.isEnabled()).thenReturn(true);
        when(cameraService.getRuntimeStreamUrl(7L, "SUB"))
                .thenReturn("rtsp://operator:secret@192.0.2.10/private");
        RuntimePreviewClient.Session runtimeSession = runtimeSession();
        when(runtimePreviewClient.createSession(eq(3L), eq(1L), eq(7L), anyString(), eq("SUB")))
                .thenReturn(runtimeSession);

        PreviewSessionRespVO result = previewService.createPreview(7L, 3L, "MAIN", 1L, 9L);

        assertEquals("session-1", result.getSessionId());
        assertEquals("/admin-api/ai-video/camera/preview/media/session-1/index.m3u8",
                result.getManifestUrl());
        assertFalse(result.toString().contains("secret"));
        assertEquals(3L, result.getNodeId());
        verify(runtimePreviewClient).createSession(3L, 1L, 7L,
                "rtsp://operator:secret@192.0.2.10/private", "SUB");
    }

    @Test
    void createPreviewMustRejectDisabledRuntimeBeforeDecryptingCamera() {
        when(runtimePreviewClient.isEnabled()).thenReturn(false);

        ServiceException exception = assertThrows(ServiceException.class,
                () -> previewService.createPreview(7L, 3L, "MAIN", 1L, 9L));

        assertEquals(1_020_000_121, exception.getCode());
        verifyNoInteractions(cameraService);
    }

    @Test
    void previewSessionMustBeBoundToTenantAndUser() {
        when(runtimePreviewClient.isEnabled()).thenReturn(true);
        when(cameraService.getRuntimeStreamUrl(7L, "SUB")).thenReturn("rtsp://192.0.2.10/live");
        when(runtimePreviewClient.createSession(anyLong(), anyLong(), anyLong(), anyString(), anyString()))
                .thenReturn(runtimeSession());
        previewService.createPreview(7L, 3L, "MAIN", 1L, 9L);

        ServiceException exception = assertThrows(ServiceException.class,
                () -> previewService.getPreview("session-1", 1L, 10L));

        assertEquals(1_020_000_124, exception.getCode());
        verify(runtimePreviewClient, never()).getSession(anyLong(), anyLong(), anyString());
    }

    @Test
    @SuppressWarnings("unchecked")
    void overlayMustBeValidatedAndSentOnlyToOwningPreviewUser() {
        when(runtimePreviewClient.isEnabled()).thenReturn(true);
        when(cameraService.getRuntimeStreamUrl(7L, "SUB")).thenReturn("rtsp://192.0.2.10/live");
        when(runtimePreviewClient.createSession(anyLong(), anyLong(), anyLong(), anyString(), anyString()))
                .thenReturn(runtimeSession());
        previewService.createPreview(7L, 3L, "MAIN", 1L, 9L);
        NodeOverlayReportReqVO overlay = overlay();

        previewService.publishOverlay(overlay, 3L);

        verify(taskService).validateRuntimeOverlay(3L, 11L,
                "11111111-1111-1111-1111-111111111111", 7L);
        ArgumentCaptor<Object> payload = ArgumentCaptor.forClass(Object.class);
        verify(webSocketSenderApi).sendObject(eq(2), eq(9L),
                eq(PreviewServiceImpl.OVERLAY_MESSAGE_TYPE), payload.capture());
        Map<String, Object> envelope = (Map<String, Object>) payload.getValue();
        assertEquals("preview.overlay.frame", envelope.get("type"));
        assertEquals("1.0", envelope.get("version"));
        Map<String, Object> data = (Map<String, Object>) envelope.get("data");
        assertEquals("session-1", data.get("sessionId"));
        assertEquals(7L, data.get("cameraId"));
        assertEquals("frame-1", data.get("frameId"));
        assertEquals(11L, data.get("taskId"));
        assertEquals(overlay.getRunId(), data.get("runId"));
        assertEquals(overlay.getImageBase64(), data.get("imageBase64"));
    }

    @Test
    @SuppressWarnings("unchecked")
    void sameCameraOtherNodeOverlayKeepsSourceIdentityAndTenantIsolation() {
        when(runtimePreviewClient.isEnabled()).thenReturn(true);
        when(cameraService.getRuntimeStreamUrl(7L, "SUB")).thenReturn("rtsp://192.0.2.10/live");
        when(runtimePreviewClient.createSession(anyLong(), anyLong(), anyLong(), anyString(), anyString())).thenReturn(runtimeSession());
        previewService.createPreview(7L, 3L, "SUB", 1L, 9L);
        NodeOverlayReportReqVO value=overlay();value.setFrameKey("abcdef0123456789abcdef0123456789");
        previewService.publishOverlay(value, 4L);
        verify(taskService).validateRuntimeOverlay(4L,11L,value.getRunId(),7L);
        ArgumentCaptor<Object> payload=ArgumentCaptor.forClass(Object.class);
        verify(webSocketSenderApi).sendObject(eq(2),eq(9L),eq(PreviewServiceImpl.OVERLAY_MESSAGE_TYPE),payload.capture());
        Map<String,Object> data=(Map<String,Object>)((Map<String,Object>)payload.getValue()).get("data");
        assertEquals(4L,data.get("nodeId"));assertEquals(value.getFrameKey(),data.get("frameKey"));
        clearInvocations(taskService,webSocketSenderApi);
        TenantContextHolder.setTenantId(2L);previewService.publishOverlay(value,4L);
        verifyNoInteractions(taskService,webSocketSenderApi);
    }

    @Test
    void overlayWithoutActivePreviewMustBeDiscardedBeforeTaskLookup() {
        previewService.publishOverlay(overlay(), 3L);

        verifyNoInteractions(taskService, webSocketSenderApi);
    }

    @Test
    void abandonedPreviewDoesNotKeepReceivingFramesAndAnotherUserCannotRenewIt() {
        AtomicLong now = new AtomicLong();
        ReflectionTestUtils.setField(previewService, "monotonicNanos", (LongSupplier) now::get);
        when(runtimePreviewClient.isEnabled()).thenReturn(true);
        when(cameraService.getRuntimeStreamUrl(7L, "SUB")).thenReturn("rtsp://192.0.2.10/sub");
        when(runtimePreviewClient.createSession(anyLong(), anyLong(), anyLong(), anyString(), anyString()))
                .thenReturn(runtimeSession());
        previewService.createPreview(7L, 3L, "SUB", 1L, 9L);
        now.set(TimeUnit.SECONDS.toNanos(80));
        assertThrows(ServiceException.class, () -> previewService.getPreview("session-1", 1L, 10L));
        now.set(TimeUnit.SECONDS.toNanos(91));
        previewService.publishOverlay(overlay(), 3L);
        verifyNoInteractions(taskService, webSocketSenderApi);
        assertThrows(ServiceException.class, () -> previewService.getPreview("session-1", 1L, 9L));
    }

    @Test
    void statusPollingRenewsTheOwningPreviewLease() {
        AtomicLong now = new AtomicLong();
        ReflectionTestUtils.setField(previewService, "monotonicNanos", (LongSupplier) now::get);
        when(runtimePreviewClient.isEnabled()).thenReturn(true);
        when(cameraService.getRuntimeStreamUrl(7L, "SUB")).thenReturn("rtsp://192.0.2.10/sub");
        when(runtimePreviewClient.createSession(anyLong(), anyLong(), anyLong(), anyString(), anyString()))
                .thenReturn(runtimeSession());
        when(runtimePreviewClient.getSession(3L, 1L, "session-1")).thenReturn(runtimeSession());
        previewService.createPreview(7L, 3L, "SUB", 1L, 9L);
        now.set(TimeUnit.SECONDS.toNanos(80));
        previewService.getPreview("session-1", 1L, 9L);
        now.set(TimeUnit.SECONDS.toNanos(100));
        previewService.publishOverlay(overlay(), 3L);
        verify(webSocketSenderApi).sendObject(eq(2), eq(9L), anyString(), any());
    }

    @Test
    void createWebRtcPreviewMustUseSubStreamAndReturnAnswer() {
        when(runtimePreviewClient.isEnabled()).thenReturn(true);
        when(cameraService.getRuntimeStreamUrl(7L, "SUB"))
                .thenReturn("rtsp://operator:secret@192.0.2.10/sub");
        RuntimePreviewClient.Session runtimeSession = webRtcSession();
        when(runtimePreviewClient.createWebRtcSession(3L, 1L, 7L,
                "rtsp://operator:secret@192.0.2.10/sub", "offer-sdp", "offer"))
                .thenReturn(runtimeSession);

        PreviewSessionRespVO result = previewService.createWebRtcPreview(
                7L, 3L, "offer-sdp", "offer", 1L, 9L);

        assertEquals("WEBRTC", result.getProtocol());
        assertEquals("answer-sdp", result.getAnswerSdp());
        assertEquals("answer", result.getAnswerType());
        assertNull(result.getManifestUrl());
        verify(cameraService).getRuntimeStreamUrl(7L, "SUB");
    }

    @Test
    void webRtcSessionStatusAndReleaseMustUseWebRtcTunnelActions() {
        when(runtimePreviewClient.isEnabled()).thenReturn(true);
        when(cameraService.getRuntimeStreamUrl(7L, "SUB")).thenReturn("rtsp://192.0.2.10/sub");
        when(runtimePreviewClient.createWebRtcSession(anyLong(), anyLong(), anyLong(),
                anyString(), anyString(), anyString())).thenReturn(webRtcSession());
        when(runtimePreviewClient.getWebRtcSession(3L, 1L, "session-1"))
                .thenReturn(webRtcSession());
        previewService.createWebRtcPreview(7L, 3L, "offer-sdp", "offer", 1L, 9L);

        PreviewSessionRespVO status = previewService.getPreview("session-1", 1L, 9L);
        previewService.releasePreview("session-1", 1L, 9L);

        assertEquals("WEBRTC", status.getProtocol());
        verify(runtimePreviewClient).getWebRtcSession(3L, 1L, "session-1");
        verify(runtimePreviewClient).releaseWebRtcSession(3L, 1L, "session-1");
        verify(runtimePreviewClient, never()).getSession(anyLong(), anyLong(), anyString());
        verify(runtimePreviewClient, never()).releaseSession(anyLong(), anyLong(), anyString());
    }

    private static RuntimePreviewClient.Session runtimeSession() {
        RuntimePreviewClient.Session session = new RuntimePreviewClient.Session();
        session.setSessionId("session-1");
        session.setCameraId(7L);
        session.setProtocol("HLS");
        session.setState("READY");
        session.setSubscriberCount(1);
        session.setDiagnosticId("diagnostic-1");
        return session;
    }

    private static RuntimePreviewClient.Session webRtcSession() {
        RuntimePreviewClient.Session session = runtimeSession();
        session.setProtocol("WEBRTC");
        session.setState("CONNECTING");
        session.setAnswerSdp("answer-sdp");
        session.setAnswerType("answer");
        return session;
    }

    private static NodeOverlayReportReqVO overlay() {
        NodeOverlayReportReqVO.BoundingBox bbox = new NodeOverlayReportReqVO.BoundingBox();
        bbox.setX(0.1);
        bbox.setY(0.2);
        bbox.setWidth(0.3);
        bbox.setHeight(0.4);
        NodeOverlayReportReqVO.OverlayObject object = new NodeOverlayReportReqVO.OverlayObject();
        object.setTrackId("track-1");
        object.setClassName("person");
        object.setConfidence(0.93);
        object.setBbox(bbox);
        object.setAttributes(Map.of());
        NodeOverlayReportReqVO overlay = new NodeOverlayReportReqVO();
        overlay.setTaskId(11L);
        overlay.setRunId("11111111-1111-1111-1111-111111111111");
        overlay.setCameraId(7L);
        overlay.setFrameId("frame-1");
        overlay.setTimestamp(Instant.parse("2026-09-03T08:00:00Z"));
        overlay.setSourceWidth(1920);
        overlay.setSourceHeight(1080);
        overlay.setObjects(List.of(object));
        overlay.setImageBase64("/9j/2Q==");
        return overlay;
    }

}
