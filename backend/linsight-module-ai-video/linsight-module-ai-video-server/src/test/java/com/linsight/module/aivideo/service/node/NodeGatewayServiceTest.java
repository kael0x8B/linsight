package com.linsight.module.aivideo.service.node;

import com.linsight.framework.tenant.core.context.TenantContextHolder;
import com.linsight.module.aivideo.integration.runtime.NodePreviewTunnelHandler;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.Map;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class NodeGatewayServiceTest {
    private final NodeService nodes = mock(NodeService.class);
    private final NodePreviewTunnelHandler tunnel = mock(NodePreviewTunnelHandler.class);
    private final NodeGatewayService service = new NodeGatewayService();
    private final com.linsight.module.aivideo.service.task.TaskService tasks = mock(com.linsight.module.aivideo.service.task.TaskService.class);
    private final com.linsight.module.aivideo.service.camera.CameraService cameras = mock(com.linsight.module.aivideo.service.camera.CameraService.class);
    private final com.linsight.module.aivideo.service.model.ModelService models = mock(com.linsight.module.aivideo.service.model.ModelService.class);
    private final com.linsight.module.aivideo.service.model.ModelExecutionService executions = mock(com.linsight.module.aivideo.service.model.ModelExecutionService.class);
    private final com.linsight.module.aivideo.service.algorithm.AlgorithmService algorithms = mock(com.linsight.module.aivideo.service.algorithm.AlgorithmService.class);

    NodeGatewayServiceTest() {
        ReflectionTestUtils.setField(service, "nodeService", nodes);
        ReflectionTestUtils.setField(service, "tunnel", tunnel);
        ReflectionTestUtils.setField(service, "taskService", tasks);
        ReflectionTestUtils.setField(service, "cameraService", cameras);
        ReflectionTestUtils.setField(service, "modelService", models);
        ReflectionTestUtils.setField(service, "modelExecutionService", executions);
        ReflectionTestUtils.setField(service, "algorithmService", algorithms);
        TenantContextHolder.setTenantId(7L);
    }

    @AfterEach void cleanup() { TenantContextHolder.clear(); }

    @Test void platformModelCannotBypassDurableUninstallThroughLocalEntrance() {
        when(executions.hasDeploymentOnNode(122L, 1L)).thenReturn(true);
        assertThat(service.invoke(1L, "model.uninstall", Map.of("modelVersionId", 122)))
                .containsEntry("ok", false).containsEntry("code", 409);
        verifyNoInteractions(tunnel);
    }

    @Test void rejectsAnUnknownOrCrossTenantNodeBeforeAnyTunnelCall() {
        doThrow(new IllegalArgumentException("node unavailable")).when(nodes).validateNodeExists(99L);
        assertThatThrownBy(() -> service.invoke(99L, "snapshot", Map.of()))
                .isInstanceOf(IllegalArgumentException.class);
        verifyNoInteractions(tunnel);
    }

    @Test void carriesTenantAndUnmodifiedRevisionToTheSingleGatewayWriter() {
        Map<String, Object> change = Map.of("taskId", 3, "expectedRevision", 12, "enabled", false);
        Map<String, Object> reply = Map.of("ok", false, "code", 409, "message", "configuration conflict");
        when(tunnel.request(eq(1L), eq(7L), eq("gateway.rpc"), anyMap()))
                .thenReturn(new NodePreviewTunnelHandler.TunnelResult(reply, null, null));
        assertThat(service.invoke(1L, "task.save", change)).isEqualTo(reply);
        verify(tunnel).request(1L, 7L, "gateway.rpc", Map.of("action", "task.save", "payload", change));
    }

    @Test void platformStreamSwitchResolvesSecretOnServerWithoutReturningItToBrowser() {
        var task = new com.linsight.module.aivideo.dal.dataobject.task.TaskDO();
        task.setId(3L); task.setNodeId(1L); task.setCameraId(4L);
        when(tasks.getTask(3L)).thenReturn(task);
        when(cameras.getRuntimeStreamUrl(4L, "MAIN")).thenReturn("rtsp://user:secret@camera/main");
        when(tunnel.request(eq(1L), eq(7L), eq("gateway.rpc"), anyMap()))
                .thenReturn(new NodePreviewTunnelHandler.TunnelResult(Map.of("ok", true), null, null));
        Map<String, Object> payload = Map.of("taskId", 3, "platformManaged", true,
                "streamTypeChanged", true,
                "configuration", Map.of("cameraId", 4,
                        "parameters", Map.of("schemaVersion", "1.0", "streamType", "MAIN")));

        assertThat(service.invoke(1L, "task.save", payload)).isEqualTo(Map.of("ok", true));
        @SuppressWarnings("unchecked")
        var sent = org.mockito.ArgumentCaptor.forClass(Map.class);
        verify(tunnel).request(eq(1L), eq(7L), eq("gateway.rpc"), sent.capture());
        Map<?, ?> envelope = sent.getValue();
        Map<?, ?> forwarded = (Map<?, ?>) envelope.get("payload");
        Map<?, ?> configuration = (Map<?, ?>) forwarded.get("configuration");
        assertThat(configuration.get("sourceUrl")).isEqualTo("rtsp://user:secret@camera/main");
        assertThat(forwarded.containsKey("streamTypeChanged")).isFalse();
        assertThat(forwarded.containsKey("platformManaged")).isFalse();
        assertThat(payload.toString()).doesNotContain("secret");
    }

    @Test void ordinaryPlatformTaskEditDoesNotLeakBrowserOwnershipMetadataToGateway() {
        when(tunnel.request(eq(1L), eq(7L), eq("gateway.rpc"), anyMap()))
                .thenReturn(new NodePreviewTunnelHandler.TunnelResult(Map.of("ok", true), null, null));
        Map<String, Object> payload = Map.of("taskId", 3, "expectedRevision", 12,
                "platformManaged", true, "streamTypeChanged", false,
                "configuration", Map.of("cameraId", 4));

        assertThat(service.invoke(1L, "task.save", payload)).isEqualTo(Map.of("ok", true));
        @SuppressWarnings("unchecked")
        var sent = org.mockito.ArgumentCaptor.forClass(Map.class);
        verify(tunnel).request(eq(1L), eq(7L), eq("gateway.rpc"), sent.capture());
        @SuppressWarnings("unchecked")
        Map<String, Object> forwarded = (Map<String, Object>) sent.getValue().get("payload");
        assertThat(forwarded).doesNotContainKeys("platformManaged", "streamTypeChanged");
        assertThat(forwarded).containsEntry("expectedRevision", 12);
    }

    @Test void seedsBothStreamsThroughTheGatewayWriterForPreflightAndSave() {
        var task = new com.linsight.module.aivideo.dal.dataobject.task.TaskDO();
        task.setId(3L); task.setNodeId(1L); task.setCameraId(4L);
        when(tasks.getTask(3L)).thenReturn(task);
        when(cameras.getRuntimeStreamUrls(4L)).thenReturn(Map.of(
                "MAIN", "rtsp://user:secret@camera/main", "SUB", "rtsp://user:secret@camera/sub"));
        when(tunnel.request(eq(1L), eq(7L), eq("gateway.rpc"), anyMap()))
                .thenReturn(new NodePreviewTunnelHandler.TunnelResult(Map.of("ok", true), null, null));
        var payload = Map.<String, Object>of("taskId", 3, "expectedRevision", 12,
                "platformManaged", true, "syncStreamUrls", true,
                "configuration", Map.of("cameraId", 4, "parameters", Map.of("streamType", "MAIN"),
                        "streamUrls", Map.of("MAIN", "rtsp://custom/main")));
        for (String action : java.util.List.of("task.capacity.preflight", "task.save")) {
            assertThat(service.invoke(1L, action, payload)).isEqualTo(Map.of("ok", true));
        }
        @SuppressWarnings("unchecked")
        var sent = org.mockito.ArgumentCaptor.forClass(Map.class);
        verify(tunnel, times(2)).request(eq(1L), eq(7L), eq("gateway.rpc"), sent.capture());
        for (Map<?, ?> envelope : sent.getAllValues()) {
            Map<?, ?> forwarded = (Map<?, ?>) envelope.get("payload");
            Map<?, ?> configuration = (Map<?, ?>) forwarded.get("configuration");
            assertThat(configuration.get("streamUrlDefaults")).isEqualTo(Map.of(
                    "MAIN", "rtsp://user:secret@camera/main", "SUB", "rtsp://user:secret@camera/sub"));
            assertThat(configuration.get("streamUrls")).isEqualTo(Map.of("MAIN", "rtsp://custom/main"));
            assertThat(forwarded.containsKey("syncStreamUrls")).isFalse();
            assertThat(forwarded.get("expectedRevision")).isEqualTo(12);
        }
    }

    @Test void cannotSeedStreamCredentialsForAnotherCameraOrNode() {
        var task = new com.linsight.module.aivideo.dal.dataobject.task.TaskDO();
        task.setId(3L); task.setNodeId(2L); task.setCameraId(4L);
        when(tasks.getTask(3L)).thenReturn(task);
        var payload = Map.<String, Object>of("taskId", 3, "platformManaged", true,
                "syncStreamUrls", true,
                "configuration", Map.of("cameraId", 4, "parameters", Map.of("streamType", "MAIN")));
        assertThat(service.invoke(1L, "task.save", payload)).containsEntry("code", 409);
        verifyNoInteractions(cameras, tunnel);
    }

    @Test void offlineGatewayDoesNotReportSuccess() {
        when(tunnel.request(anyLong(), anyLong(), anyString(), anyMap())).thenThrow(
                new NodePreviewTunnelHandler.TunnelRequestException(null, "TUNNEL_NOT_CONNECTED", "offline"));
        assertThat(service.invoke(1L, "snapshot", Map.of())).containsEntry("ok", false).containsEntry("code", 503);
    }

    @Test void batchNamesAreReadOnlyAndLocalTasksDoNotBorrowPlatformIdentity() {
        var platform = Map.of("config", Map.of("taskId", 2, "cameraId", 3, "modelVersionId", 122, "algorithmId", 7));
        var local = Map.of("platformManaged", false, "config", Map.of("taskId", 9, "cameraId", 8, "modelVersionId", 125));
        Map<String, Object> data = Map.of("tasks", java.util.List.of(platform, local),
                "models", java.util.List.of(Map.of("modelVersionId", 122)));
        Map<String, Object> reply = Map.of("ok", true, "data", data);
        when(tunnel.request(anyLong(), anyLong(), anyString(), anyMap()))
                .thenReturn(new NodePreviewTunnelHandler.TunnelResult(reply, null, null));
        when(tasks.getTaskNames(java.util.Set.of(2L))).thenReturn(Map.of(2L, "现场安全帽识别"));
        when(cameras.getCameraNames(java.util.Set.of(3L))).thenReturn(Map.of(3L, "入口摄像头"));
        when(models.getVersionDisplayNames(java.util.Set.of(122L))).thenReturn(Map.of(122L, Map.of("name", "安全帽模型", "version", "v1")));
        when(algorithms.getSummaries(java.util.Set.of(7L))).thenReturn(java.util.List.of(
                new com.linsight.module.aivideo.service.algorithm.AlgorithmSummaryDTO(7L, "安全帽检测", "ppe.helmet", "SAFETY_HELMET")));
        var result = service.invoke(1L, "snapshot", Map.of());
        var names = (Map<?, ?>) ((Map<?, ?>) result.get("data")).get("names");
        assertThat(names.get("tasks")).isEqualTo(Map.of(2L, "现场安全帽识别"));
        assertThat(names.get("algorithms")).isEqualTo(Map.of(7L, "安全帽检测"));
        assertThat(data).doesNotContainKey("names");
        verify(tasks).getTaskNames(java.util.Set.of(2L));
        verify(cameras).getCameraNames(java.util.Set.of(3L));
        verify(models).getVersionDisplayNames(java.util.Set.of(122L));
        verify(executions).reconcileNodeInventory(1L, java.util.Set.of(122L));
        verify(algorithms).getSummaries(java.util.Set.of(7L));
        verifyNoMoreInteractions(tasks, cameras, models, algorithms);
    }
}
