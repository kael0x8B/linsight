package com.linsight.module.aivideo.service.algorithm;

import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.module.aivideo.dal.dataobject.algorithm.PipelineVersionDO;
import com.linsight.module.aivideo.dal.mysql.algorithm.PipelineVersionMapper;
import com.linsight.module.aivideo.service.model.ModelExecutionService;
import com.linsight.module.aivideo.service.model.ModelService;
import com.linsight.module.aivideo.service.node.NodeExecutionProviderDTO;
import com.linsight.module.aivideo.service.node.NodeModelEnvironmentDTO;
import com.linsight.module.aivideo.service.node.NodeService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class AlgorithmPackageResolutionTest {
    @Mock private PipelineVersionMapper pipelineMapper;
    @Mock private ModelService modelService;
    @Mock private ModelExecutionService modelExecutionService;
    @Mock private NodeService nodeService;
    @InjectMocks private AlgorithmPackageService service;

    private static final NodeModelEnvironmentDTO ROCKCHIP =
            new NodeModelEnvironmentDTO(true, List.of("ONNX", "RKNN", "ARCHIVE"), List.of("rk3566"));

    private Map<String, Object> option(long id, String format, String target, List<String> labels) {
        var manifest = new LinkedHashMap<String, Object>();
        manifest.put("taskType", "OBJECT_DETECTION");
        manifest.put("decoder", Map.of("type", "AUTO_DETECTION", "labels", labels));
        if (target != null) manifest.put("targetPlatform", target);
        return Map.of("id", id, "modelId", id, "format", format, "manifest", manifest);
    }

    private void catalog(List<Map<String, Object>> options, NodeModelEnvironmentDTO environment, Map<Long, String> deployments) {
        var version = new PipelineVersionDO();
        version.setValidationStatus("PUBLISHED");
        version.setPackageArtifactRef("helmet.zip");
        version.setDag(JsonUtils.toJsonString(Map.of("algorithmPackage", Map.of("manifest", Map.of("models", List.of(
                Map.of("slot", "ppe", "formats", List.of("RKNN", "ONNX"),
                        "taskType", "OBJECT_DETECTION", "labels", List.of("helmet", "no_helmet"))))))));
        when(pipelineMapper.selectById(1L)).thenReturn(version);
        when(modelService.getExecutableOptions()).thenReturn(options);
        when(modelExecutionService.getNodeDeploymentStates(2L)).thenReturn(deployments);
        when(nodeService.getModelEnvironment(2L)).thenReturn(environment);
        when(nodeService.supportsAlgorithmPackages(2L)).thenReturn(true);
    }

    @Test void newBoxSelectsMatchingAcceleratorWithoutManualModelChoice() {
        var labels = List.of("helmet", "no_helmet");
        catalog(List.of(option(9, "RKNN", "rk3588", labels), option(8, "ONNX", null, labels),
                option(7, "RKNN", "rk3566", labels), option(10, "RKNN", "rk3566", List.of("person"))), ROCKCHIP, Map.of());

        var result = service.resolve(1L, 2L);

        assertEquals(Map.of("ppe", 7L), result.get("bindings"));
        assertEquals(Map.of(), result.get("blockers"));
        verify(modelExecutionService, never()).deployModel(anyLong(), anyLong());
    }

    @Test void rk3588SelectsItsOwnArtifactFromTheSameAlgorithmRole() {
        var labels = List.of("helmet", "no_helmet");
        var rk3588 = new NodeModelEnvironmentDTO(
                true, List.of("ONNX", "RKNN", "ARCHIVE"), List.of("rk3588"));
        catalog(List.of(option(7, "RKNN", "rk3566", labels),
                option(9, "RKNN", "rk3588", labels), option(8, "ONNX", null, labels)),
                rk3588, Map.of());

        assertEquals(Map.of("ppe", 9L), service.resolve(1L, 2L).get("bindings"));
    }

    @Test void installedCompatibleVersionIsReusedAndSelectionDoesNotDependOnCatalogOrder() {
        var labels = List.of("helmet", "no_helmet");
        catalog(List.of(option(8, "RKNN", "rk3566", labels), option(7, "RKNN", null, labels)), ROCKCHIP, Map.of(7L, "READY"));
        assertEquals(Map.of("ppe", 7L), service.resolve(1L, 2L).get("bindings"));
    }

    @Test void cpuBoxNeverSelectsAnIncompatibleNpuModelEvenIfStaleInventorySaysReady() {
        var labels = List.of("helmet", "no_helmet");
        catalog(List.of(option(7, "RKNN", "rk3566", labels), option(8, "ONNX", null, labels)),
                new NodeModelEnvironmentDTO(true, List.of("ONNX"), List.of()), Map.of(7L, "READY"));
        assertEquals(Map.of("ppe", 8L), service.resolve(1L, 2L).get("bindings"));
    }

    @Test void missingTargetBlocksAutomaticInstallationWithActionableReason() {
        catalog(List.of(option(7, "RKNN", null, List.of("helmet", "no_helmet"))), ROCKCHIP, Map.of());
        var result = service.resolve(1L, 2L);
        assertEquals(Map.of(), result.get("bindings"));
        assertTrue(result.get("blockers").toString().contains("适用目标"));
    }

    @Test void olderNodesKeepPortableModelsAndProvenInstalledModelsAvailable() {
        assertEquals("", AlgorithmPackageService.deploymentBlocker("ONNX", Map.of(), NodeModelEnvironmentDTO.unknown(), false));
        assertFalse(AlgorithmPackageService.deploymentBlocker("ONNX", Map.of("execution", Map.of(
                "provider", "cuda", "target", "sm_87")), NodeModelEnvironmentDTO.unknown(), false).isEmpty());
        assertFalse(AlgorithmPackageService.deploymentBlocker("RKNN", Map.of(), NodeModelEnvironmentDTO.unknown(), false).isEmpty());
        assertEquals("", AlgorithmPackageService.deploymentBlocker("RKNN", Map.of(), NodeModelEnvironmentDTO.unknown(), true));
    }

    @Test void acceleratorArchivesRequireTheAcceleratorAsWellAsArchiveSupport() {
        var runtime = Map.<String, Object>of("decoder", Map.of("type", "FACE_PAIR_SFACE_RKNN"), "targetPlatform", "rk3566");
        assertFalse(AlgorithmPackageService.deploymentBlocker("ARCHIVE", runtime,
                new NodeModelEnvironmentDTO(true, List.of("ONNX", "ARCHIVE"), List.of()), false).isEmpty());
        assertEquals("", AlgorithmPackageService.deploymentBlocker("ARCHIVE", runtime, ROCKCHIP, false));
    }

    @Test void readyAcceleratorModelRemainsUsableWhenProviderVersionWasNotReported() {
        var runtime = Map.<String, Object>of("targetPlatform", "rk3566", "execution", Map.of(
                "provider", "rknpu2", "target", "rk3566", "runtime", "rknn-toolkit-lite2",
                "minRuntimeVersion", "2.3.2"));
        var unversioned = new NodeModelEnvironmentDTO(true, List.of("RKNN"), List.of(), List.of(
                new NodeExecutionProviderDTO("rknpu2", "NPU", "rockchip", List.of("rk3566"),
                        List.of("RKNN"), "rknn-toolkit-lite2", null)));
        assertTrue(AlgorithmPackageService.deploymentBlocker(
                "RKNN", runtime, unversioned, false).contains("版本"));
        assertEquals("", AlgorithmPackageService.deploymentBlocker(
                "RKNN", runtime, unversioned, true));
        assertEquals("", AlgorithmPackageService.deploymentBlocker(
                "RKNN", runtime, ROCKCHIP, false));
    }

    @Test void futureAcceleratorsUseTheSameProviderTargetAndRuntimeContract() {
        var environment = new NodeModelEnvironmentDTO(true, List.of("TENSORRT"), List.of(), List.of(
                new NodeExecutionProviderDTO("nvidia-tensorrt", "GPU", "nvidia", List.of("sm_87"),
                        List.of("TENSORRT"), "tensorrt", "10.2.1")));
        var compatible = Map.<String, Object>of("execution", Map.of(
                "provider", "nvidia-tensorrt", "target", "sm_87",
                "runtime", "tensorrt", "minRuntimeVersion", "10.2.0"));

        assertEquals("", AlgorithmPackageService.deploymentBlocker(
                "TENSORRT", compatible, environment, false));
        assertTrue(AlgorithmPackageService.deploymentBlocker("TENSORRT", Map.of("execution", Map.of(
                "provider", "nvidia-tensorrt", "target", "sm_89", "runtime", "tensorrt")),
                environment, false).contains("目标"));
        assertTrue(AlgorithmPackageService.deploymentBlocker("TENSORRT", Map.of("execution", Map.of(
                "provider", "nvidia-tensorrt", "target", "sm_87", "runtime", "tensorrt",
                "minRuntimeVersion", "10.3.0")), environment, false).contains("版本"));
    }

    @Test void deviceSpecificArtifactsWithoutAProviderAreOnlyReusedWhenAlreadyProvenReady() {
        var environment = new NodeModelEnvironmentDTO(true, List.of("TENSORRT"), List.of(), List.of(
                new NodeExecutionProviderDTO("nvidia-tensorrt", "GPU", "nvidia", List.of("sm_87"),
                        List.of("TENSORRT"), "tensorrt", "10.2.1")));
        assertTrue(AlgorithmPackageService.deploymentBlocker(
                "TENSORRT", Map.of(), environment, false).contains("执行后端"));
        assertEquals("", AlgorithmPackageService.deploymentBlocker(
                "TENSORRT", Map.of(), environment, true));
    }
}
