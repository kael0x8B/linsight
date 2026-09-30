package com.linsight.module.aivideo.controller.admin.node;

import com.linsight.module.aivideo.service.node.NodeGatewayService;
import org.junit.jupiter.api.Test;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

class NodeGatewayValidationTest {
    private final NodeGatewayService service = mock(NodeGatewayService.class);
    private final NodeGatewayController controller = new NodeGatewayController();

    NodeGatewayValidationTest() {
        ReflectionTestUtils.setField(controller, "service", service);
    }

    private NodeGatewayController.RequestVO request(String action, Map<String, Object> payload) {
        var request = new NodeGatewayController.RequestVO();
        request.setNodeId(17L);
        request.setAction(action);
        request.setPayload(payload);
        return request;
    }

    @Test void validatesAllowlistAndSizeBeforeOpeningTunnel() {
        assertThat(controller.imageValidation(request("task.save", Map.of())).getData()).containsEntry("code", 400);
        assertThat(controller.imageValidation(request("validation.sample-save",
                Map.of("imageBase64", "a".repeat(5_592_412)))).getData()).containsEntry("code", 422);
        assertThat(controller.query(request("validation.run-create", Map.of())).getData()).containsEntry("code", 403);
        verifyNoInteractions(service);
    }

    @Test void forwardsGatewayValidationAndDiagnosticResults() {
        var payload = Map.<String, Object>of("id", "set-1");
        var reply = Map.<String, Object>of("ok", false, "code", 409, "message", "revision conflict");
        when(service.invoke(17L, "validation.run-create", payload)).thenReturn(reply);
        assertThat(controller.imageValidation(request("validation.run-create", payload)).getData()).isEqualTo(reply);
    }

    @Test void requiresBothNodeQueryAndModelTestPermissions() throws Exception {
        var method = NodeGatewayController.class.getMethod("imageValidation", NodeGatewayController.RequestVO.class);
        assertThat(method.getAnnotation(PreAuthorize.class).value())
                .isEqualTo("@ss.hasPermission('ai-video:node:query') and @ss.hasPermission('ai-video:model:test')");
    }
}
