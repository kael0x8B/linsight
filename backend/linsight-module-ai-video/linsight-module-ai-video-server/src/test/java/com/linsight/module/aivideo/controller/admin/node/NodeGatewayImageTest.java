package com.linsight.module.aivideo.controller.admin.node;

import com.linsight.module.aivideo.service.node.NodeGatewayService;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

class NodeGatewayImageTest {
    private final NodeGatewayService service = mock(NodeGatewayService.class);
    private final NodeGatewayController controller = new NodeGatewayController();

    NodeGatewayImageTest() {
        ReflectionTestUtils.setField(controller, "service", service);
    }

    private NodeGatewayController.RequestVO request(String action, Map<String, Object> payload) {
        var request = new NodeGatewayController.RequestVO();
        request.setNodeId(17L);
        request.setAction(action);
        request.setPayload(payload);
        return request;
    }

    @Test void readOnlyQueryCannotTriggerImageInference() {
        var result = controller.query(request("task.recognize-image", Map.of("taskId", 3, "imageBase64", "abcd")));
        assertThat(result.getData()).containsEntry("code", 403);
        verifyNoInteractions(service);
    }

    @Test void uploadCannotSupplyExecutionConfigurationOrInvokeAnotherAction() {
        assertThat(controller.recognizeImage(request("task.save", Map.of())).getData())
                .containsEntry("code", 422);
        assertThat(controller.recognizeImage(request("task.recognize-image",
                Map.of("taskId", 3, "imageBase64", "abcd", "sourceUrl", "file:///private"))).getData())
                .containsEntry("code", 422);
        verifyNoInteractions(service);
    }

    @Test void oversizedImageNeverEntersNodeTunnel() {
        assertThat(controller.recognizeImage(request("task.recognize-image",
                Map.of("taskId", 3, "imageBase64", "a".repeat(5_592_412)))).getData())
                .containsEntry("code", 422);
        verifyNoInteractions(service);
    }

    @Test void returnsActualGatewayResultIncludingDiagnosticId() {
        var payload = Map.<String, Object>of("taskId", 3, "imageBase64", "abcd");
        var reply = Map.<String, Object>of("ok", false, "code", 504, "diagnosticId", "image-timeout");
        when(service.invoke(17L, "task.recognize-image", payload)).thenReturn(reply);
        assertThat(controller.recognizeImage(request("task.recognize-image", payload)).getData()).isEqualTo(reply);
    }
}
