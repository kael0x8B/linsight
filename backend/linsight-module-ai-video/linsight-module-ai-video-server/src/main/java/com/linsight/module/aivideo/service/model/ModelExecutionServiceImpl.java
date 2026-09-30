package com.linsight.module.aivideo.service.model;

import cn.hutool.core.util.StrUtil;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.module.aivideo.controller.admin.model.vo.ModelTestCreateReqVO;
import com.linsight.module.aivideo.controller.node.model.vo.ModelCommandDetailRespVO;
import com.linsight.module.aivideo.dal.dataobject.model.ModelDO;
import com.linsight.module.aivideo.dal.dataobject.model.ModelDeploymentDO;
import com.linsight.module.aivideo.dal.dataobject.model.ModelTestDO;
import com.linsight.module.aivideo.dal.dataobject.model.ModelVersionDO;
import com.linsight.module.aivideo.dal.mysql.model.ModelDeploymentMapper;
import com.linsight.module.aivideo.dal.mysql.model.ModelMapper;
import com.linsight.module.aivideo.dal.mysql.model.ModelTestMapper;
import com.linsight.module.aivideo.dal.mysql.model.ModelVersionMapper;
import com.linsight.module.aivideo.framework.file.UploadContentValidator;
import com.linsight.module.aivideo.service.node.NodeCommandDTO;
import com.linsight.module.aivideo.service.node.NodeCommandService;
import com.linsight.module.infra.api.file.FileApi;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

import java.io.IOException;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Collection;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

import static com.linsight.framework.common.exception.util.ServiceExceptionUtil.exception;
import static com.linsight.module.aivideo.enums.model.ErrorCodeConstants.*;

@Service
public class ModelExecutionServiceImpl implements ModelExecutionService {
    @Override
    public Map<Long, String> getNodeDeploymentStates(Long nodeId) {
        Map<Long, String> states = new java.util.LinkedHashMap<>();
        getNodeDeployments(nodeId).forEach(d -> states.putIfAbsent(d.getModelVersionId(), d.getActualStatus()));
        return states;
    }

    @Override
    public void reconcileNodeInventory(Long nodeId, Collection<Long> installedModelVersionIds) {
        Set<Long> installed = installedModelVersionIds == null ? Set.of() : Set.copyOf(installedModelVersionIds);
        Map<Long, ModelDeploymentDO> latest = new java.util.LinkedHashMap<>();
        getNodeDeployments(nodeId).forEach(deployment -> latest.putIfAbsent(
                deployment.getModelVersionId(), deployment));
        latest.values().stream()
                .filter(deployment -> "READY".equals(deployment.getActualStatus()))
                .filter(deployment -> !installed.contains(deployment.getModelVersionId()))
                .forEach(deployment -> {
                    deployment.setActualStatus("REMOVED");
                    deployment.setErrorCode("DEVICE_INVENTORY_MISSING");
                    deployment.setErrorMessage("网关实时模型清单中已不存在该模型，平台已回收安装状态");
                    deploymentMapper.updateById(deployment);
                });
    }
    @Override
    public java.util.Map<Long, Long> getNodeCounts(java.util.Collection<Long> nodeIds) {
        if (nodeIds.isEmpty()) return java.util.Map.of();
        var query = new com.baomidou.mybatisplus.core.conditions.query.QueryWrapper<ModelDeploymentDO>()
                .select("node_id", "COUNT(DISTINCT model_version_id) AS node_count").in("node_id", nodeIds).groupBy("node_id");
        query.eq("actual_status", "READY");
        query.apply("config_version = (SELECT MAX(latest.config_version) FROM ai_model_deployment latest WHERE latest.model_version_id = ai_model_deployment.model_version_id AND latest.node_id = ai_model_deployment.node_id AND latest.tenant_id = ai_model_deployment.tenant_id AND latest.deleted = 0)");
        java.util.Map<Long, Long> result = new java.util.HashMap<>();
        for (var row : deploymentMapper.selectMaps(query)) {
            result.put(((Number) row.get("node_id")).longValue(), ((Number) row.get("node_count")).longValue());
        }
        return result;
    }
    private static final int INITIAL_CONFIG_VERSION = 1;
    private static final long IMAGE_MAX_BYTES = 10L * 1024 * 1024;
    private static final Set<String> EXECUTABLE_ARTIFACT_FORMATS = Set.of(
            "ONNX", "TORCHSCRIPT", "PYTORCH", "ARCHIVE", "RKNN");

    @Resource private com.linsight.module.aivideo.service.node.NodeService nodeService;
    @Resource private ModelMapper modelMapper;
    @Resource private ModelVersionMapper modelVersionMapper;
    @Resource private ModelDeploymentMapper deploymentMapper;
    @Resource private ModelTestMapper testMapper;
    @Resource private NodeCommandService nodeCommandService;
    @Resource private FileApi fileApi;
    @Resource private TransactionTemplate transactionTemplate;

    @Override
    public Long deployModel(Long modelVersionId, Long nodeId) {
        SupportedVersion supported = requireSupportedVersion(modelVersionId);
        ModelDeploymentDO existing = deploymentMapper.selectByVersionAndNode(modelVersionId, nodeId);
        if (existing != null && !Set.of("FAILED", "REMOVED").contains(existing.getActualStatus())) {
            return existing.getId();
        }
        String blocker = ModelDeploymentCompatibility.deploymentBlocker(
                supported.version().getArtifactFormat(), supported.runtimeManifest(),
                nodeService.getModelEnvironment(nodeId), false);
        if (!blocker.isEmpty()) throw exception(MODEL_NODE_INCOMPATIBLE, blocker);
        int configVersion = existing == null ? INITIAL_CONFIG_VERSION : existing.getConfigVersion() + 1;
        return transactionTemplate.execute(status -> {
            String commandId = UUID.randomUUID().toString();
            ModelDeploymentDO deployment = new ModelDeploymentDO();
            deployment.setModelVersionId(modelVersionId);
            deployment.setNodeId(nodeId);
            deployment.setConfigVersion(configVersion);
            deployment.setDesiredStatus("READY");
            deployment.setActualStatus("QUEUED");
            deployment.setCommandId(commandId);
            deploymentMapper.insert(deployment);
            nodeCommandService.createCommand(commandId, nodeId, "DEPLOY_MODEL", deployment.getId(),
                    configVersion, "model-deploy:" + modelVersionId + ":" + nodeId + ":" + configVersion);
            return deployment.getId();
        });
    }

    @Override
    public boolean hasDeploymentOnNode(Long modelVersionId, Long nodeId) {
        return deploymentMapper.selectByVersionAndNode(modelVersionId, nodeId) != null;
    }

    @Override
    public Long uninstallModel(Long modelVersionId, Long nodeId) {
        if (!nodeService.supportsModelUninstall(nodeId)) throw exception(MODEL_UNINSTALL_UNSUPPORTED);
        requireVersion(modelVersionId);
        var existing = deploymentMapper.selectByVersionAndNode(modelVersionId, nodeId);
        if (existing == null) throw exception(MODEL_DEPLOYMENT_NOT_FOUND);
        if ("REMOVED".equals(existing.getActualStatus()) || "REMOVING".equals(existing.getActualStatus())) return existing.getId();
        if (!Set.of("READY", "FAILED").contains(existing.getActualStatus())) throw exception(MODEL_DEPLOYMENT_NOT_READY);
        return transactionTemplate.execute(status -> {
            var deployment = new ModelDeploymentDO();
            String commandId = UUID.randomUUID().toString();
            deployment.setModelVersionId(modelVersionId);
            deployment.setNodeId(nodeId);
            deployment.setConfigVersion(existing.getConfigVersion() + 1);
            deployment.setDesiredStatus("REMOVED");
            deployment.setActualStatus("REMOVING");
            deployment.setCommandId(commandId);
            deploymentMapper.insert(deployment);
            nodeCommandService.createCommand(commandId, nodeId, "UNINSTALL_MODEL", deployment.getId(),
                    deployment.getConfigVersion(), "model-uninstall:" + modelVersionId + ":" + nodeId + ":" + deployment.getConfigVersion());
            return deployment.getId();
        });
    }

    @Override
    public List<ModelDeploymentDO> getNodeDeployments(Long nodeId) {
        return deploymentMapper.selectList(new com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX<ModelDeploymentDO>()
                .eq(ModelDeploymentDO::getNodeId, nodeId).orderByDesc(ModelDeploymentDO::getConfigVersion));
    }

    @Override
    public List<ModelDeploymentDO> getDeployments(Long modelVersionId) {
        requireVersion(modelVersionId);
        return deploymentMapper.selectListByVersion(modelVersionId);
    }

    @Override
    public List<ModelDeploymentDO> getDeployments(Collection<Long> modelVersionIds) {
        if (modelVersionIds == null || modelVersionIds.isEmpty()) {
            return List.of();
        }
        return deploymentMapper.selectListByVersions(modelVersionIds);
    }

    @Override
    public Long createTest(ModelTestCreateReqVO reqVO) throws IOException {
        requireSupportedVersion(reqVO.getModelVersionId());
        ModelDeploymentDO deployment = deploymentMapper.selectByVersionAndNode(
                reqVO.getModelVersionId(), reqVO.getNodeId());
        if (deployment == null || !"READY".equals(deployment.getActualStatus())) {
            throw exception(MODEL_DEPLOYMENT_NOT_READY);
        }
        byte[] image = reqVO.getFile().getBytes();
        if (image.length == 0 || image.length > IMAGE_MAX_BYTES) {
            throw exception(MODEL_TEST_IMAGE_INVALID);
        }
        String contentType = UploadContentValidator.detectImageContentType(image);
        String claimedContentType = StrUtil.blankToDefault(reqVO.getFile().getContentType(), "");
        if (contentType == null || !contentType.equals(claimedContentType)) {
            throw exception(MODEL_TEST_IMAGE_INVALID);
        }
        String imageName;
        try {
            imageName = UploadContentValidator.safeFileName(
                    reqVO.getFile().getOriginalFilename(), "test-image");
        } catch (IllegalArgumentException error) {
            throw exception(MODEL_TEST_IMAGE_INVALID);
        }
        String imageRef = fileApi.createFile(image, imageName, "ai-video/model-test", contentType);
        Map<String, Object> parameters = Map.of(
                "schemaVersion", "1.0",
                "confidence", reqVO.getConfidence(),
                "nmsThreshold", reqVO.getNmsThreshold(),
                "inputWidth", reqVO.getInputWidth(),
                "inputHeight", reqVO.getInputHeight(),
                "outputCoordinates", "NORMALIZED_XYWH"
        );
        return transactionTemplate.execute(status -> {
            String commandId = UUID.randomUUID().toString();
            ModelTestDO test = new ModelTestDO();
            test.setModelVersionId(reqVO.getModelVersionId());
            test.setNodeId(reqVO.getNodeId());
            test.setImageRef(imageRef);
            test.setImageName(imageName);
            test.setParameters(JsonUtils.toJsonString(parameters));
            test.setStatus("QUEUED");
            test.setCommandId(commandId);
            testMapper.insert(test);
            nodeCommandService.createCommand(commandId, reqVO.getNodeId(), "RUN_MODEL_TEST", test.getId(),
                    INITIAL_CONFIG_VERSION, "model-test:" + test.getId());
            return test.getId();
        });
    }

    @Override
    public ModelTestDO getTest(Long id) {
        ModelTestDO test = testMapper.selectById(id);
        if (test == null) throw exception(MODEL_TEST_NOT_FOUND);
        return test;
    }

    @Override
    public List<ModelTestDO> getTests(Long modelVersionId) {
        requireVersion(modelVersionId);
        return testMapper.selectListByVersion(modelVersionId);
    }

    @Override
    public ModelCommandDetailRespVO getCommandDetail(String commandId, Long nodeId) {
        NodeCommandDTO command = nodeCommandService.getCommandForNode(commandId, nodeId);
        ModelDeploymentDO deployment = Set.of("DEPLOY_MODEL", "UNINSTALL_MODEL").contains(command.getCommandType())
                ? deploymentMapper.selectByCommandId(commandId) : null;
        ModelTestDO test = "RUN_MODEL_TEST".equals(command.getCommandType())
                ? testMapper.selectByCommandId(commandId) : null;
        if (deployment == null && test == null) {
            throw exception(MODEL_DEPLOYMENT_NOT_FOUND);
        }
        Long versionId = deployment != null ? deployment.getModelVersionId() : test.getModelVersionId();
        if ("UNINSTALL_MODEL".equals(command.getCommandType())) {
            var version = requireVersion(versionId);
            var detail = new ModelCommandDetailRespVO();
            detail.setCommandId(commandId);
            detail.setCommandType(command.getCommandType());
            detail.setConfigVersion(command.getConfigVersion());
            detail.setModelVersionId(versionId);
            detail.setSha256(version.getSha256());
            detail.setArtifactUrl("");
            detail.setArtifactName(version.getArtifactName());
            detail.setArtifactFormat(version.getArtifactFormat());
            detail.setTrustedArtifact(false);
            return detail;
        }
        SupportedVersion supported = requireSupportedVersion(versionId);
        ModelVersionDO version = supported.version();

        ModelCommandDetailRespVO detail = new ModelCommandDetailRespVO();
        detail.setCommandId(commandId);
        detail.setCommandType(command.getCommandType());
        detail.setConfigVersion(command.getConfigVersion());
        detail.setModelVersionId(versionId);
        detail.setModelName(supported.model().getName());
        detail.setModelVersion(version.getVersion());
        detail.setArtifactUrl(fileApi.presignGetUrl(version.getArtifactRef(), 600).getCheckedData());
        detail.setArtifactName(version.getArtifactName());
        detail.setArtifactFormat(version.getArtifactFormat());
        detail.setTrustedArtifact("PRESET".equals(supported.model().getSourceType()));
        detail.setSha256(version.getSha256());
        detail.setRuntimeManifest(supported.runtimeManifest());
        if (test != null) {
            detail.setImageUrl(fileApi.presignGetUrl(test.getImageRef(), 600).getCheckedData());
            detail.setImageName(test.getImageName());
            detail.setParameters(JsonUtils.parseMap(test.getParameters()));
        }
        return detail;
    }

    @Override
    public void validateFaceVerificationReady(Long modelVersionId, Long nodeId) {
        var supported = requireSupportedVersion(modelVersionId);
        var decoder = supported.runtimeManifest().get("decoder");
        if (!(decoder instanceof Map<?, ?> values)
                || !java.util.Set.of("FACE_PAIR_SFACE", "FACE_PAIR_SFACE_RKNN").contains(values.get("type"))) {
            throw exception(MODEL_RUNTIME_MANIFEST_INVALID);
        }
        validateDeploymentReady(modelVersionId, nodeId);
    }

    @Override
    public void validateDeploymentReady(Long modelVersionId, Long nodeId) {
        ModelDeploymentDO deployment = deploymentMapper.selectByVersionAndNode(modelVersionId, nodeId);
        if (deployment == null || !"READY".equals(deployment.getActualStatus())) {
            throw exception(MODEL_DEPLOYMENT_NOT_READY);
        }
    }

    @Override
    public void applyCommandReport(NodeCommandDTO report) {
        transactionTemplate.executeWithoutResult(status -> {
            if (Set.of("DEPLOY_MODEL", "UNINSTALL_MODEL").contains(report.getCommandType())) {
                applyDeploymentReport(report);
            } else if ("RUN_MODEL_TEST".equals(report.getCommandType())) {
                applyTestReport(report);
            }
        });
    }

    private void applyDeploymentReport(NodeCommandDTO report) {
        ModelDeploymentDO deployment = deploymentMapper.selectByCommandId(report.getCommandId());
        if (deployment == null) throw exception(MODEL_DEPLOYMENT_NOT_FOUND);
        String stage = StrUtil.blankToDefault(report.getStage(), "RUNNING");
        if ("READY".equals(stage) || "COMPLETED".equals(stage)) {
            stage = "RUNNING";
        }
        deployment.setActualStatus(Set.of("FAILED", "EXPIRED").contains(report.getStatus())
                ? "FAILED" : stage);
        deployment.setDiagnosticId(report.getDiagnosticId());
        deployment.setBackend(report.getBackend());
        deployment.setDevice(report.getDevice());
        deployment.setErrorCode(report.getErrorCode());
        deployment.setErrorMessage(report.getErrorMessage());
        if ("SUCCEEDED".equals(report.getStatus())) {
            deployment.setActualStatus("UNINSTALL_MODEL".equals(report.getCommandType()) ? "REMOVED" : "READY");
            deployment.setReadyTime(LocalDateTime.now());
        }
        deploymentMapper.updateById(deployment);
    }

    private void applyTestReport(NodeCommandDTO report) {
        ModelTestDO test = testMapper.selectByCommandId(report.getCommandId());
        if (test == null) throw exception(MODEL_TEST_NOT_FOUND);
        test.setStatus(report.getStatus());
        test.setDiagnosticId(report.getDiagnosticId());
        test.setBackend(report.getBackend());
        test.setPreprocessMillis(report.getPreprocessMillis());
        test.setInferenceMillis(report.getInferenceMillis());
        test.setPostprocessMillis(report.getPostprocessMillis());
        test.setErrorCode(report.getErrorCode());
        test.setErrorMessage(report.getErrorMessage());
        if ("SUCCEEDED".equals(report.getStatus())) {
            validateStandardResult(report.getResult());
            test.setResult(JsonUtils.toJsonString(report.getResult()));
            test.setFinishTime(LocalDateTime.now());
        } else if ("FAILED".equals(report.getStatus())) {
            test.setFinishTime(LocalDateTime.now());
        }
        testMapper.updateById(test);
        if ("SUCCEEDED".equals(report.getStatus())) {
            promoteExecutionReady(test.getModelVersionId(), test.getNodeId());
        }
    }

    private void promoteExecutionReady(Long versionId, Long nodeId) {
        ModelDeploymentDO deployment = deploymentMapper.selectByVersionAndNode(versionId, nodeId);
        if (deployment == null || !"READY".equals(deployment.getActualStatus())
                || !testMapper.existsSucceededByVersionAndNode(versionId, nodeId)) {
            return;
        }
        ModelVersionDO version = requireVersion(versionId);
        if ("READY".equals(version.getExecutionStatus())) {
            return;
        }
        version.setExecutionStatus("READY");
        version.setExecutionReadyTime(LocalDateTime.now());
        modelVersionMapper.updateById(version);
    }

    private SupportedVersion requireSupportedVersion(Long versionId) {
        ModelVersionDO version = requireVersion(versionId);
        ModelDO model = modelMapper.selectById(version.getModelId());
        if (model == null || !EXECUTABLE_ARTIFACT_FORMATS.contains(version.getArtifactFormat())) {
            throw exception(MODEL_ADAPTER_ONNX_REQUIRED);
        }
        final Map<String, Object> runtimeManifest;
        try {
            ModelServiceImpl.validateRuntimeManifest(version.getRuntimeManifest());
            runtimeManifest = JsonUtils.parseMap(version.getRuntimeManifest());
        } catch (RuntimeException error) {
            throw exception(MODEL_RUNTIME_MANIFEST_INVALID);
        }
        if (!"PUBLISHED".equals(version.getPublishStatus())) {
            throw exception(MODEL_VERSION_NOT_PUBLISHED);
        }
        return new SupportedVersion(version, model, runtimeManifest);
    }

    private record SupportedVersion(ModelVersionDO version, ModelDO model,
                                    Map<String, Object> runtimeManifest) {}

    private ModelVersionDO requireVersion(Long versionId) {
        ModelVersionDO version = modelVersionMapper.selectById(versionId);
        if (version == null) throw exception(MODEL_VERSION_NOT_FOUND);
        return version;
    }

    @SuppressWarnings("unchecked")
    private static void validateStandardResult(Map<String, Object> result) {
        if (result == null || !"1.0".equals(result.get("schemaVersion"))
                || !(result.get("sourceWidth") instanceof Number width) || width.intValue() <= 0
                || !(result.get("sourceHeight") instanceof Number height) || height.intValue() <= 0
                || !(result.get("objects") instanceof List<?> objects) || objects.size() > 500) {
            throw exception(MODEL_TEST_RESULT_INVALID);
        }
        for (Object value : objects) {
            if (!(value instanceof Map<?, ?> object) || !(object.get("class") instanceof String)
                    || !(object.get("confidence") instanceof Number confidence)
                    || confidence.doubleValue() < 0 || confidence.doubleValue() > 1
                    || !(object.get("bbox") instanceof Map<?, ?> bbox)) {
                throw exception(MODEL_TEST_RESULT_INVALID);
            }
            for (String key : List.of("x", "y", "width", "height")) {
                Object coordinate = bbox.get(key);
                if (!(coordinate instanceof Number number) || number.doubleValue() < 0
                        || number.doubleValue() > 1) throw exception(MODEL_TEST_RESULT_INVALID);
            }
            double x = ((Number) bbox.get("x")).doubleValue();
            double y = ((Number) bbox.get("y")).doubleValue();
            double boxWidth = ((Number) bbox.get("width")).doubleValue();
            double boxHeight = ((Number) bbox.get("height")).doubleValue();
            if (x + boxWidth > 1.000001 || y + boxHeight > 1.000001) {
                throw exception(MODEL_TEST_RESULT_INVALID);
            }
        }
    }
}
