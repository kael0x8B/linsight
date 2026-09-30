package com.linsight.module.aivideo.service.model;

import com.linsight.framework.common.exception.ServiceException;
import com.linsight.module.aivideo.dal.dataobject.model.ModelDeploymentDO;
import com.linsight.module.aivideo.dal.dataobject.model.ModelDO;
import com.linsight.module.aivideo.dal.dataobject.model.ModelTestDO;
import com.linsight.module.aivideo.dal.dataobject.model.ModelVersionDO;
import com.linsight.module.aivideo.dal.mysql.model.ModelDeploymentMapper;
import com.linsight.module.aivideo.dal.mysql.model.ModelMapper;
import com.linsight.module.aivideo.dal.mysql.model.ModelTestMapper;
import com.linsight.module.aivideo.dal.mysql.model.ModelVersionMapper;
import com.linsight.module.aivideo.service.node.NodeCommandDTO;
import com.linsight.module.aivideo.service.node.NodeCommandService;
import com.linsight.module.aivideo.service.node.NodeModelEnvironmentDTO;
import com.linsight.module.infra.api.file.FileApi;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.TransactionCallback;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.List;
import java.util.Map;
import java.util.function.Consumer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.when;
import org.springframework.web.multipart.MultipartFile;
import com.linsight.module.aivideo.controller.admin.model.vo.ModelTestCreateReqVO;

@ExtendWith(MockitoExtension.class)
class ModelExecutionServiceImplTest {

    @Mock private com.linsight.module.aivideo.service.node.NodeService nodeService;
    @Mock private ModelMapper modelMapper;
    @Mock private ModelVersionMapper modelVersionMapper;
    @Mock private ModelDeploymentMapper deploymentMapper;
    @Mock private ModelTestMapper testMapper;
    @Mock private NodeCommandService nodeCommandService;
    @Mock private FileApi fileApi;
    @Mock private TransactionTemplate transactionTemplate;
    @InjectMocks private ModelExecutionServiceImpl service;

    @BeforeEach
    @SuppressWarnings("unchecked")
    void runTransactionsImmediately() {
        lenient().doAnswer(invocation -> {
            invocation.<Consumer<TransactionStatus>>getArgument(0).accept(null);
            return null;
        }).when(transactionTemplate).executeWithoutResult(any());
    }

    @Test
    void uninstallStagesAreAcceptedByNodeReportContract() {
        try (var factory = jakarta.validation.Validation.buildDefaultValidatorFactory()) {
            var report = new com.linsight.module.aivideo.controller.node.node.vo.NodeCommandReportReqVO();
            report.setCommandId("11111111-1111-1111-1111-111111111111");
            report.setDiagnosticId("22222222-2222-2222-2222-222222222222");
            report.setStatus("RUNNING"); report.setStage("REMOVING");
            assertEquals(0, factory.getValidator().validate(report).size());
            report.setStatus("SUCCEEDED"); report.setStage("REMOVED");
            assertEquals(0, factory.getValidator().validate(report).size());
        }
    }

    @Test
    void oldAgentMustNeverReceiveUninstallCommand() {
        when(nodeService.supportsModelUninstall(20L)).thenReturn(false);
        assertThrows(ServiceException.class, () -> service.uninstallModel(10L, 20L));
        org.mockito.Mockito.verifyNoInteractions(nodeCommandService);
    }

    @Test
    void uninstallOnlyBecomesRemovedAfterSuccessfulAcknowledgement() {
        ModelDeploymentDO deployment = new ModelDeploymentDO();
        deployment.setActualStatus("REMOVING");
        when(deploymentMapper.selectByCommandId("remove-1")).thenReturn(deployment);
        NodeCommandDTO report = new NodeCommandDTO();
        report.setCommandId("remove-1"); report.setCommandType("UNINSTALL_MODEL");
        report.setStatus("RUNNING"); report.setStage("REMOVING");
        service.applyCommandReport(report);
        assertEquals("REMOVING", deployment.getActualStatus());
        report.setStatus("SUCCEEDED"); report.setStage("REMOVED");
        service.applyCommandReport(report);
        assertEquals("REMOVED", deployment.getActualStatus());
    }

    @Test
    void liveGatewayInventoryReclaimsStaleReadyDeployment() {
        ModelDeploymentDO missing = new ModelDeploymentDO();
        missing.setModelVersionId(121L);
        missing.setActualStatus("READY");
        ModelDeploymentDO installed = new ModelDeploymentDO();
        installed.setModelVersionId(128L);
        installed.setActualStatus("READY");
        when(deploymentMapper.selectList(any())).thenReturn(List.of(missing, installed));

        service.reconcileNodeInventory(20L, List.of(128L));

        assertEquals("REMOVED", missing.getActualStatus());
        assertEquals("DEVICE_INVENTORY_MISSING", missing.getErrorCode());
        assertEquals("READY", installed.getActualStatus());
        verify(deploymentMapper).updateById(missing);
        verify(deploymentMapper, never()).updateById(installed);
    }

    @Test
    void failedDeploymentRetryMustCreateNextConfigVersion() {
        when(transactionTemplate.execute(any())).thenAnswer(invocation ->
                invocation.<TransactionCallback<?>>getArgument(0).doInTransaction(null));
        ModelDO model = new ModelDO();
        model.setId(1L);
        model.setCode("person-detection");
        ModelVersionDO version = new ModelVersionDO();
        version.setId(10L);
        version.setModelId(1L);
        version.setArtifactFormat("ONNX");
        version.setPublishStatus("PUBLISHED");
        version.setRuntimeManifest(runtimeManifest());
        ModelDeploymentDO failed = new ModelDeploymentDO();
        failed.setId(29L);
        failed.setConfigVersion(2);
        failed.setActualStatus("FAILED");
        when(modelVersionMapper.selectById(10L)).thenReturn(version);
        when(modelMapper.selectById(1L)).thenReturn(model);
        when(deploymentMapper.selectByVersionAndNode(10L, 20L)).thenReturn(failed);
        doAnswer(invocation -> {
            invocation.<ModelDeploymentDO>getArgument(0).setId(30L);
            return 1;
        }).when(deploymentMapper).insert(any(ModelDeploymentDO.class));

        Long deploymentId = service.deployModel(10L, 20L);

        assertEquals(30L, deploymentId);
        verify(nodeCommandService).createCommand(any(), org.mockito.ArgumentMatchers.eq(20L),
                org.mockito.ArgumentMatchers.eq("DEPLOY_MODEL"),
                org.mockito.ArgumentMatchers.eq(30L), org.mockito.ArgumentMatchers.eq(3),
                org.mockito.ArgumentMatchers.eq("model-deploy:10:20:3"));
    }

    @Test
    void incompatibleAcceleratorTargetIsRejectedBeforeCreatingACommand() {
        ModelDO model = new ModelDO();
        model.setId(1L);
        ModelVersionDO version = new ModelVersionDO();
        version.setId(10L);
        version.setModelId(1L);
        version.setArtifactFormat("RKNN");
        version.setPublishStatus("PUBLISHED");
        version.setRuntimeManifest(runtimeManifest().replace("\"preprocess\":{",
                "\"targetPlatform\":\"rk3588\",\"preprocess\":{"));
        when(modelVersionMapper.selectById(10L)).thenReturn(version);
        when(modelMapper.selectById(1L)).thenReturn(model);
        when(nodeService.getModelEnvironment(20L)).thenReturn(
                new NodeModelEnvironmentDTO(true, List.of("RKNN"), List.of("rk3566")));

        ServiceException error = assertThrows(ServiceException.class,
                () -> service.deployModel(10L, 20L));

        assertEquals(1_020_001_029, error.getCode());
        verify(nodeCommandService, never()).createCommand(any(), any(), any(), any(), any(), any());
    }

    @Test
    void controlledPresetAdapterCanCreateModelTest() throws Exception {
        when(transactionTemplate.execute(any())).thenAnswer(invocation ->
                invocation.<TransactionCallback<?>>getArgument(0).doInTransaction(null));
        ModelDO model = new ModelDO();
        model.setId(5L);
        model.setCode("flame");
        ModelVersionDO version = new ModelVersionDO();
        version.setId(15L);
        version.setModelId(5L);
        version.setArtifactFormat("ONNX");
        version.setPublishStatus("PUBLISHED");
        version.setRuntimeManifest(runtimeManifest());
        ModelDeploymentDO deployment = new ModelDeploymentDO();
        deployment.setActualStatus("READY");
        MultipartFile file = org.mockito.Mockito.mock(MultipartFile.class);
        when(file.getBytes()).thenReturn(new byte[]{(byte) 0xff, (byte) 0xd8, (byte) 0xff, (byte) 0xd9});
        when(file.getContentType()).thenReturn("image/jpeg");
        when(file.getOriginalFilename()).thenReturn("flame.jpg");
        when(fileApi.createFile(any(), any(), any(), any())).thenReturn("test/image");
        when(modelVersionMapper.selectById(15L)).thenReturn(version);
        when(modelMapper.selectById(5L)).thenReturn(model);
        when(deploymentMapper.selectByVersionAndNode(15L, 20L)).thenReturn(deployment);
        doAnswer(invocation -> {
            invocation.<ModelTestDO>getArgument(0).setId(31L);
            return 1;
        }).when(testMapper).insert(any(ModelTestDO.class));
        ModelTestCreateReqVO request = new ModelTestCreateReqVO();
        request.setModelVersionId(15L);
        request.setNodeId(20L);
        request.setFile(file);
        request.setConfidence(0.5);
        request.setNmsThreshold(0.5);
        request.setInputWidth(640);
        request.setInputHeight(640);

        assertEquals(31L, service.createTest(request));
    }

    @Test
    void modelTestMustRejectMimeSpoofingBeforeObjectStorage() throws Exception {
        ModelDO model = new ModelDO();
        model.setId(5L);
        model.setCode("flame");
        ModelVersionDO version = new ModelVersionDO();
        version.setId(15L);
        version.setModelId(5L);
        version.setArtifactFormat("ONNX");
        version.setPublishStatus("PUBLISHED");
        version.setRuntimeManifest(runtimeManifest());
        ModelDeploymentDO deployment = new ModelDeploymentDO();
        deployment.setActualStatus("READY");
        MultipartFile file = org.mockito.Mockito.mock(MultipartFile.class);
        when(file.getBytes()).thenReturn(new byte[]{'M', 'Z', 0, 0});
        when(file.getContentType()).thenReturn("image/jpeg");
        when(modelVersionMapper.selectById(15L)).thenReturn(version);
        when(modelMapper.selectById(5L)).thenReturn(model);
        when(deploymentMapper.selectByVersionAndNode(15L, 20L)).thenReturn(deployment);
        ModelTestCreateReqVO request = new ModelTestCreateReqVO();
        request.setModelVersionId(15L);
        request.setNodeId(20L);
        request.setFile(file);

        ServiceException error = assertThrows(ServiceException.class, () -> service.createTest(request));

        assertEquals(1_020_001_024, error.getCode());
        org.mockito.Mockito.verify(fileApi, org.mockito.Mockito.never())
                .createFile(any(), any(), any(), any());
    }

    @Test
    void successfulStandardTestMustPromoteVersionAfterReadyDeployment() {
        ModelTestDO test = test();
        ModelDeploymentDO deployment = new ModelDeploymentDO();
        deployment.setActualStatus("READY");
        ModelVersionDO version = new ModelVersionDO();
        version.setId(10L);
        version.setExecutionStatus("NOT_READY");
        when(testMapper.selectByCommandId("test-command")).thenReturn(test);
        when(deploymentMapper.selectByVersionAndNode(10L, 20L)).thenReturn(deployment);
        when(testMapper.existsSucceededByVersionAndNode(10L, 20L)).thenReturn(true);
        when(modelVersionMapper.selectById(10L)).thenReturn(version);

        service.applyCommandReport(successReport(validResult()));

        assertEquals("SUCCEEDED", test.getStatus());
        assertEquals("READY", version.getExecutionStatus());
        verify(modelVersionMapper).updateById(version);
    }

    @Test
    void successfulTestMustRejectOutOfRangeStandardCoordinates() {
        when(testMapper.selectByCommandId("test-command")).thenReturn(test());
        Map<String, Object> invalid = validResult();
        invalid.put("objects", List.of(Map.of(
                "class", "person", "confidence", 0.9,
                "bbox", Map.of("x", 1.1, "y", 0.1, "width", 0.2, "height", 0.3))));

        ServiceException error = assertThrows(ServiceException.class,
                () -> service.applyCommandReport(successReport(invalid)));

        assertEquals(1_020_001_026, error.getCode());
    }

    private static ModelTestDO test() {
        ModelTestDO test = new ModelTestDO();
        test.setId(30L);
        test.setCommandId("test-command");
        test.setModelVersionId(10L);
        test.setNodeId(20L);
        test.setStatus("RUNNING");
        return test;
    }

    private static String runtimeManifest() {
        return "{\"schemaVersion\":\"1.0\",\"taskType\":\"OBJECT_DETECTION\"," +
                "\"preprocess\":{\"color\":\"RGB\",\"layout\":\"NCHW\",\"dtype\":\"FLOAT32\"}," +
                "\"decoder\":{\"type\":\"AUTO_DETECTION\",\"labels\":[\"person\"]}}";
    }

    private static NodeCommandDTO successReport(Map<String, Object> result) {
        NodeCommandDTO report = new NodeCommandDTO();
        report.setCommandId("test-command");
        report.setCommandType("RUN_MODEL_TEST");
        report.setStatus("SUCCEEDED");
        report.setResult(result);
        return report;
    }

    private static Map<String, Object> validResult() {
        return new java.util.HashMap<>(Map.of(
                "schemaVersion", "1.0",
                "sourceWidth", 1280,
                "sourceHeight", 720,
                "objects", List.of(Map.of(
                        "class", "person", "confidence", 0.9,
                        "bbox", Map.of("x", 0.1, "y", 0.1, "width", 0.2, "height", 0.3)))));
    }
}
