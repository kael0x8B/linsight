package com.linsight.module.aivideo.service.node;

import com.linsight.framework.common.exception.ServiceException;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.module.aivideo.controller.node.node.vo.NodeHeartbeatReqVO;
import com.linsight.module.aivideo.dal.dataobject.node.EdgeNodeDO;
import com.linsight.module.aivideo.dal.mysql.node.EdgeNodeMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class NodeModelEnvironmentTest {
    @Mock private EdgeNodeMapper edgeNodeMapper;
    @InjectMocks private NodeServiceImpl service;

    private EdgeNodeDO node(Map<String, Object> snapshot) {
        var node = new EdgeNodeDO();
        node.setStatus(0);
        node.setOnlineStatus(1);
        node.setResourceSnapshot(JsonUtils.toJsonString(snapshot));
        when(edgeNodeMapper.selectById(1L)).thenReturn(node);
        return node;
    }

    @Test void projectsOnlyAuthenticatedRuntimeEnvironment() {
        node(Map.of("runtimeStatus", "UP", "modelEnvironment", Map.of(
                "schemaVersion", "1.0", "formats", List.of("ONNX", "RKNN"), "rknnTargets", List.of("rk3566"))));
        assertEquals(new NodeModelEnvironmentDTO(true, List.of("ONNX", "RKNN"), List.of("rk3566")),
                service.getModelEnvironment(1L));
        assertEquals("2.3.2", service.getModelEnvironment(1L).providers().get(0).runtimeVersion());
    }

    @Test void projectsGenericExecutionProvidersForFutureNodeTypes() {
        var provider = new NodeExecutionProviderDTO("nvidia-tensorrt", "GPU", "nvidia",
                List.of("sm_87"), List.of("TENSORRT"), "tensorrt", "10.2.0");
        node(Map.of("runtimeStatus", "UP", "modelEnvironment", Map.of(
                "schemaVersion", "1.0", "formats", List.of("TENSORRT"), "rknnTargets", List.of(),
                "providers", List.of(Map.of(
                        "code", "nvidia-tensorrt", "deviceType", "GPU", "vendor", "nvidia",
                        "targets", List.of("sm_87"), "formats", List.of("TENSORRT"),
                        "runtime", "tensorrt", "runtimeVersion", "10.2.0")))));

        assertEquals(new NodeModelEnvironmentDTO(true, List.of("TENSORRT"), List.of(), List.of(provider)),
                service.getModelEnvironment(1L));
    }

    @Test void missingOrDownRuntimeDoesNotInventAcceleratorSupport() {
        var node = node(Map.of("runtimeStatus", "UP"));
        assertEquals(NodeModelEnvironmentDTO.unknown(), service.getModelEnvironment(1L));
        node.setResourceSnapshot(JsonUtils.toJsonString(Map.of("runtimeStatus", "DOWN", "modelEnvironment", Map.of(
                "schemaVersion", "1.0", "formats", List.of("RKNN"), "rknnTargets", List.of("rk3566")))));
        assertEquals(NodeModelEnvironmentDTO.unknown(), service.getModelEnvironment(1L));
    }

    @Test void heartbeatContractAcceptsAProviderWithoutKnowingItsHardwareInAdvance() {
        var provider = new NodeHeartbeatReqVO.ModelEnvironment.ExecutionProvider();
        provider.setCode("nvidia-tensorrt");
        provider.setDeviceType("GPU");
        provider.setVendor("nvidia");
        provider.setTargets(List.of("sm_87"));
        provider.setFormats(List.of("TENSORRT"));
        provider.setRuntime("tensorrt");
        provider.setRuntimeVersion("10.2.0");
        var environment = new NodeHeartbeatReqVO.ModelEnvironment();
        environment.setSchemaVersion("1.0");
        environment.setFormats(List.of("TENSORRT"));
        environment.setRknnTargets(List.of());
        environment.setProviders(List.of(provider));

        try (var factory = jakarta.validation.Validation.buildDefaultValidatorFactory()) {
            assertTrue(factory.getValidator().validate(environment).isEmpty());
        }
    }

    @Test void offlineNodeCannotBeUsedForNewDeployment() {
        node(Map.of()).setOnlineStatus(0);
        assertThrows(ServiceException.class, () -> service.getModelEnvironment(1L));
    }
}
