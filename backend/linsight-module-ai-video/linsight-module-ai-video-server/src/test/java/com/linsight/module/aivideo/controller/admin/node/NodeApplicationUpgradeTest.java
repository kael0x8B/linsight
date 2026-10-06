package com.linsight.module.aivideo.controller.admin.node;

import com.linsight.module.aivideo.service.node.NodeGatewayService;
import org.junit.jupiter.api.Test;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

class NodeApplicationUpgradeTest {
    private final NodeGatewayService service = mock(NodeGatewayService.class);
    private final NodeGatewayController controller = new NodeGatewayController();

    NodeApplicationUpgradeTest() { ReflectionTestUtils.setField(controller, "service", service); }

    private NodeGatewayController.RequestVO request(String action, Map<String, Object> payload) {
        var request = new NodeGatewayController.RequestVO();
        request.setNodeId(17L);
        request.setAction(action);
        request.setPayload(payload);
        return request;
    }

    @Test void upgradeWritesCannotUseReadOnlyRouteOrArbitraryActions() {
        assertThat(controller.query(request("app-upgrade.install", Map.of())).getData()).containsEntry("code", 403);
        assertThat(controller.applicationUpgrade(request("task.save", Map.of())).getData()).containsEntry("code", 400);
        assertThat(controller.applicationUpgrade(request("app-upgrade.upload.chunk",
                Map.of("data", "a".repeat(349_529)))).getData()).containsEntry("code", 413);
        verifyNoInteractions(service);
    }

    @Test void forwardsBoundedChunkUsingExistingTenantCheckedNodeService() {
        var payload = Map.<String, Object>of("id", "upload-id", "offset", 0, "data", "YWJj");
        when(service.invoke(17L, "app-upgrade.upload.chunk", payload)).thenReturn(Map.of("ok", true));
        assertThat(controller.applicationUpgrade(request("app-upgrade.upload.chunk", payload)).getData()).containsEntry("ok", true);
        verify(service).invoke(17L, "app-upgrade.upload.chunk", payload);
    }

    @Test void requiresUpgradePermission() throws Exception {
        var method = NodeGatewayController.class.getMethod("applicationUpgrade", NodeGatewayController.RequestVO.class);
        assertThat(method.getAnnotation(PreAuthorize.class).value()).isEqualTo("@ss.hasPermission('ai-video:node:upgrade')");
    }
}
