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

    NodeGatewayServiceTest() {
        ReflectionTestUtils.setField(service, "nodeService", nodes);
        ReflectionTestUtils.setField(service, "tunnel", tunnel);
        ReflectionTestUtils.setField(service, "taskService", tasks);
        ReflectionTestUtils.setField(service, "cameraService", cameras);
        ReflectionTestUtils.setField(service, "modelService", models);
        TenantContextHolder.setTenantId(7L);
    }

    @AfterEach void cleanup() { TenantContextHolder.clear(); }

    @Test void platformModelCannotBypassDurableUninstallThroughLocalEntrance() {
        var executions = mock(com.linsight.module.aivideo.service.model.ModelExecutionService.class);
        ReflectionTestUtils.setField(service, "modelExecutionService", executions);
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

    @Test void offlineGatewayDoesNotReportSuccess() {
        when(tunnel.request(anyLong(), anyLong(), anyString(), anyMap())).thenThrow(
                new NodePreviewTunnelHandler.TunnelRequestException(null, "TUNNEL_NOT_CONNECTED", "offline"));
        assertThat(service.invoke(1L, "snapshot", Map.of())).containsEntry("ok", false).containsEntry("code", 503);
    }

    @Test void batchNamesAreReadOnlyAndLocalTasksDoNotBorrowPlatformIdentity() {
        var platform = Map.of("config", Map.of("taskId", 2, "cameraId", 3, "modelVersionId", 122));
        var local = Map.of("platformManaged", false, "config", Map.of("taskId", 9, "cameraId", 8, "modelVersionId", 125));
        Map<String, Object> data = Map.of("tasks", java.util.List.of(platform, local),
                "models", java.util.List.of(Map.of("modelVersionId", 122)));
        Map<String, Object> reply = Map.of("ok", true, "data", data);
        when(tunnel.request(anyLong(), anyLong(), anyString(), anyMap()))
                .thenReturn(new NodePreviewTunnelHandler.TunnelResult(reply, null, null));
        when(tasks.getTaskNames(java.util.Set.of(2L))).thenReturn(Map.of(2L, "现场安全帽识别"));
        when(cameras.getCameraNames(java.util.Set.of(3L))).thenReturn(Map.of(3L, "入口摄像头"));
        when(models.getVersionDisplayNames(java.util.Set.of(122L))).thenReturn(Map.of(122L, Map.of("name", "安全帽模型", "version", "v1")));
        var result = service.invoke(1L, "snapshot", Map.of());
        var names = (Map<?, ?>) ((Map<?, ?>) result.get("data")).get("names");
        assertThat(names.get("tasks")).isEqualTo(Map.of(2L, "现场安全帽识别"));
        assertThat(data).doesNotContainKey("names");
        verify(tasks).getTaskNames(java.util.Set.of(2L));
        verify(cameras).getCameraNames(java.util.Set.of(3L));
        verify(models).getVersionDisplayNames(java.util.Set.of(122L));
        verifyNoMoreInteractions(tasks, cameras, models);
    }
}
