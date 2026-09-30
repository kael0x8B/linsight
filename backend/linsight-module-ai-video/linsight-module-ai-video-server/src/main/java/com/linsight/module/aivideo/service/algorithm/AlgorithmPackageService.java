package com.linsight.module.aivideo.service.algorithm;

import cn.hutool.crypto.digest.DigestUtil;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.module.aivideo.controller.admin.algorithm.vo.AlgorithmSaveReqVO;
import com.linsight.module.aivideo.dal.dataobject.algorithm.PipelineVersionDO;
import com.linsight.module.aivideo.dal.mysql.algorithm.AlgorithmMapper;
import com.linsight.module.aivideo.dal.mysql.algorithm.PipelineVersionMapper;
import com.linsight.module.aivideo.service.model.ModelDeploymentCompatibility;
import com.linsight.module.aivideo.service.node.NodeModelEnvironmentDTO;
import com.linsight.module.infra.api.file.FileApi;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import java.util.*;
import static com.linsight.module.aivideo.service.algorithm.AlgorithmPackageValidator.*;

/** Package metadata is owned by algorithm; node downloads use short-lived object URLs. */
@Service
public class AlgorithmPackageService {
    @Resource private AlgorithmService algorithmService;
    @Resource private AlgorithmMapper algorithmMapper;
    @Resource private PipelineVersionMapper pipelineMapper;
    @Resource private FileApi fileApi;
    @Resource private TransactionTemplate transactionTemplate;
    @Resource private com.linsight.module.aivideo.service.model.ModelService modelService;
    @Resource private com.linsight.module.aivideo.service.model.ModelExecutionService modelExecutionService;
    @Resource private com.linsight.module.aivideo.service.node.NodeService nodeService;
    @Resource private FaceReferenceService faceReferenceService;

    public Map<String, Object> resources(Map<String, Object> dag, Map<String, Object> parameters, Map<String, Long> bindings, boolean download) {
        Map<String, Object> result = new LinkedHashMap<>();
        if (!(dag.get("algorithmPackage") instanceof Map<?, ?> descriptor)) return result;
        var manifest = map(descriptor.get("manifest"));
        var config = map(parameters.getOrDefault("algorithm", Map.of()));
        for (Object value : (List<?>) manifest.getOrDefault("resources", List.of())) {
            var resource = map(value);
            if (!"FACE_LIBRARY".equals(resource.get("type"))) throw invalid("资源类型不支持");
            if (!(config.get(resource.get("parameter")) instanceof Number libraryId)) throw invalid("请选择对比人员库");
            Long version = bindings.get(resource.get("modelSlot"));
            if (version == null) throw invalid("人员库未绑定识别模型");
            List<?> selected = config.get(resource.get("selectionParameter")) instanceof List<?> ids ? ids : List.of();
            var references = faceReferenceService.ready(libraryId.longValue(), version).stream()
                    .filter(r -> selected.isEmpty() || selected.stream().anyMatch(id -> id instanceof Number n && n.longValue() == r.getEntryId())).toList();
            if (references.isEmpty() || references.size() > 256 || (!selected.isEmpty() && selected.size() != references.size())) throw invalid("人员库没有与当前模型匹配的有效特征，或选择的人员尚未就绪");
            List<Map<String, Object>> entries = new ArrayList<>();
            for (var reference : references) {
                Map<String, Object> entry = new LinkedHashMap<>();
                entry.put("id", reference.getEntryId()); entry.put("name", reference.getName());
                entry.put("sha256", reference.getSha256()); entry.put("modelSlot", resource.get("modelSlot"));
                entry.put("validUntil", reference.getValidUntil().atZone(java.time.ZoneId.systemDefault()).toInstant().toEpochMilli());
                if (download) entry.put("url", fileApi.presignGetUrl(reference.getObjectRef(), 600).getCheckedData());
                entries.add(entry);
            }
            result.put((String) resource.get("key"), entries);
        }
        return result;
    }

    public Map<String, Object> resolve(Long pipelineId, Long nodeId) {
        nodeService.validateNodeExists(nodeId);
        var version = pipelineMapper.selectById(pipelineId);
        if (version == null || !"PUBLISHED".equals(version.getValidationStatus()) || version.getPackageArtifactRef() == null) throw invalid("算法包版本尚未发布");
        var manifest = map(map(JsonUtils.parseMap(version.getDag()).get("algorithmPackage")).get("manifest"));
        var deployments = modelExecutionService.getNodeDeploymentStates(nodeId);
        var options = modelService.getExecutableOptions();
        var environment = nodeService.getModelEnvironment(nodeId);
        Map<String, Object> roles = new LinkedHashMap<>();
        Map<String, Long> bindings = new LinkedHashMap<>();
        Map<String, String> blockers = new LinkedHashMap<>();
        for (Object value : (List<?>) manifest.get("models")) {
            var role = map(value);
            var candidates = options.stream().filter(o -> compatible(role, (String) o.get("format"), o.get("manifest") instanceof Map<?, ?> contract ? map(contract) : Map.of()))
                    .map(o -> {
                        Map<String, Object> option = new LinkedHashMap<>(o);
                        option.remove("manifest");
                        boolean installed = "READY".equals(deployments.get(((Number) o.get("id")).longValue()));
                        var runtime = o.get("manifest") instanceof Map<?, ?> contract ? map(contract) : Map.<String, Object>of();
                        var requirement = ModelDeploymentCompatibility.executionRequirement(
                                (String) o.get("format"), runtime);
                        String reason = deploymentBlocker((String) o.get("format"), runtime, environment, installed);
                        if (requirement.provider() != null) option.put("executionProvider", requirement.provider());
                        if (requirement.target() != null) option.put("executionTarget", requirement.target());
                        if (requirement.runtime() != null) option.put("executionRuntime", requirement.runtime());
                        if (requirement.minimumRuntimeVersion() != null) {
                            option.put("minimumRuntimeVersion", requirement.minimumRuntimeVersion());
                        }
                        option.put("installed", installed);
                        option.put("deployable", reason.isEmpty());
                        option.put("reason", reason);
                        option.put("recommended", false);
                        return option;
                    }).sorted(Comparator.<Map<String, Object>>comparingInt(o -> Boolean.TRUE.equals(o.get("deployable")) ? 0 : 1)
                            .thenComparingInt(o -> Boolean.TRUE.equals(o.get("installed")) ? 0 : 1)
                            .thenComparingInt(o -> o.get("executionProvider") != null ? 0 : 1)
                            .thenComparingInt(o -> Boolean.TRUE.equals(o.get("defaultVersion")) ? 0 : 1)
                            .thenComparing(Comparator.comparingLong((Map<String, Object> o) -> ((Number) o.get("id")).longValue()).reversed())).toList();
            String slot = (String) role.get("slot");
            roles.put(slot, candidates);
            candidates.stream().filter(o -> Boolean.TRUE.equals(o.get("deployable"))).findFirst()
                    .ifPresentOrElse(o -> {
                        bindings.put(slot, ((Number) o.get("id")).longValue());
                        o.put("recommended", true);
                    }, () -> blockers.put(slot, candidates.isEmpty()
                            ? "算法资源尚未准备好，请联系管理员补齐已发布且通过测试的兼容模型"
                            : candidates.stream().map(o -> (String) o.get("reason")).distinct().collect(java.util.stream.Collectors.joining("；"))));
        }
        return Map.of("manifest", manifest, "roles", roles, "bindings", bindings,
                "blockers", blockers, "environmentReported", environment != null && environment.reported(),
                "supported", nodeService.supportsAlgorithmPackages(nodeId));
    }

    static String deploymentBlocker(String format, Map<String, Object> runtime,
            NodeModelEnvironmentDTO environment, boolean installed) {
        return ModelDeploymentCompatibility.deploymentBlocker(format, runtime, environment, installed);
    }

    public static boolean compatible(Map<String, Object> role, String format, Map<String, Object> runtime) {
        if (runtime == null) runtime = Map.of();
        if (role.get("formats") instanceof List<?> formats && !formats.contains(format)) return false;
        if (role.get("taskType") instanceof String type && !type.equals(runtime.get("taskType"))) return false;
        var decoder = runtime.get("decoder") instanceof Map<?, ?> value ? map(value) : Map.<String, Object>of();
        List<?> labels = decoder.get("labels") instanceof List<?> value ? value : List.of();
        return !(role.get("labels") instanceof List<?> required) || labels.containsAll(required);
    }

    public void validateBinding(Map<String, Object> dag, String slot, String format, String runtimeManifest) {
        if (!(dag.get("algorithmPackage") instanceof Map<?, ?> descriptor)) return;
        for (Object value : (List<?>) map(descriptor.get("manifest")).get("models")) {
            var role = map(value);
            if (slot.equals(role.get("slot")) && !compatible(role, format, JsonUtils.parseMap(runtimeManifest))) {
                throw invalid("模型与算法角色 " + slot + " 的输入输出要求不兼容");
            }
        }
    }

    public Map<String, Object> upload(byte[] content) {
        Map<String, Object> manifest = inspect(content);
        String digest = DigestUtil.sha256Hex(content);
        String code = (String) manifest.get("code");
        var existing = algorithmMapper.selectByCode(code);
        if (existing != null) {
            if (existing.getCapabilityKey() == null || !existing.getCapabilityKey().equals("package." + code)) throw invalid("算法编码已被已有算法占用，请使用其他编码");
            for (var version : pipelineMapper.selectListByAlgorithm(existing.getId())) {
                Object value = JsonUtils.parseMap(version.getDag()).get("algorithmPackage");
                if (!(value instanceof Map<?, ?> descriptor)) continue;
                var previous = map(descriptor.get("manifest"));
                if (Objects.equals(previous.get("version"), manifest.get("version"))) {
                    if (!digest.equals(descriptor.get("sha256"))) throw invalid("同一版本不可覆盖，请增加算法版本号");
                    return result(version, manifest, digest);
                }
            }
        }
        String artifact = fileApi.createFile(content, code + ".zip", "ai-video/algorithm/" + code, "application/zip");
        return transactionTemplate.execute(status -> {
            var current = algorithmMapper.selectByCode(code);
            Long algorithmId;
            if (current == null) {
                AlgorithmSaveReqVO request = new AlgorithmSaveReqVO();
                request.setCode(code); request.setName((String) manifest.get("name"));
                request.setCategory("CUSTOM"); request.setSceneGroup(String.valueOf(manifest.getOrDefault("category", "GENERAL")));
                request.setImplementationType("COMPOSITE"); request.setDescription(String.valueOf(manifest.getOrDefault("description", "")));
                request.setCapabilityKey("package." + code); request.setStatus(0);
                request.setParameterSchema(Map.of("schemaVersion", "1.0", "type", "object", "properties", Map.of("algorithm", manifest.getOrDefault("parameterSchema", Map.of()))));
                request.setDefaultParameters(Map.of("schemaVersion", "1.0", "sampleFps", 1, "confidence", 0.5, "inputWidth", 640, "inputHeight", 640, "nmsThreshold", 0.5,
                        "algorithm", manifest.getOrDefault("defaultParameters", Map.of())));
                request.setEventType(String.valueOf(manifest.getOrDefault("eventType", "ALGORITHM_EVENT")));
                algorithmId = algorithmService.createAlgorithm(request);
            } else algorithmId = current.getId();
            var latest = pipelineMapper.selectLatestByAlgorithm(algorithmId);
            PipelineVersionDO version = new PipelineVersionDO();
            version.setAlgorithmId(algorithmId); version.setVersion(latest == null ? 1 : latest.getVersion() + 1);
            List<Map<String, Object>> nodes = new ArrayList<>();
            for (Object model : (List<?>) manifest.get("models")) {
                String slot = (String) map(model).get("slot");
                nodes.add(Map.of("id", slot, "type", "DETECTOR", "capabilityKey", "model." + slot));
            }
            version.setDag(JsonUtils.toJsonString(Map.of("schemaVersion", "1.0", "nodes", nodes, "edges", List.of(),
                    "algorithmPackage", Map.of("sha256", digest, "manifest", manifest))));
            version.setPackageArtifactRef(artifact); version.setValidationStatus("VALID");
            pipelineMapper.insert(version);
            return result(version, manifest, digest);
        });
    }

    public List<Map<String, Object>> list() {
        List<Map<String, Object>> result = new ArrayList<>();
        var versions = pipelineMapper.selectList(new com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX<PipelineVersionDO>()
                .isNotNull(PipelineVersionDO::getPackageArtifactRef).orderByDesc(PipelineVersionDO::getId));
        var algorithms = versions.isEmpty() ? Map.<Long, com.linsight.module.aivideo.dal.dataobject.algorithm.AlgorithmDO>of()
                : algorithmMapper.selectBatchIds(versions.stream().map(PipelineVersionDO::getAlgorithmId).distinct().toList()).stream()
                .collect(java.util.stream.Collectors.toMap(a -> a.getId(), a -> a));
        for (var version : versions) {
            var descriptor = map(JsonUtils.parseMap(version.getDag()).get("algorithmPackage"));
            result.add(result(version, map(descriptor.get("manifest")), (String) descriptor.get("sha256"), algorithms.get(version.getAlgorithmId())));
        }
        return result;
    }

    public String eventType(Long pipelineId, String fallback) {
        var version = pipelineMapper.selectById(pipelineId);
        if (version == null || version.getPackageArtifactRef() == null) return fallback;
        var manifest = map(map(JsonUtils.parseMap(version.getDag()).get("algorithmPackage")).get("manifest"));
        return String.valueOf(manifest.getOrDefault("eventType", "ALGORITHM_EVENT"));
    }

    public boolean isPackageVersion(Long pipelineId) {
        var version = pipelineMapper.selectById(pipelineId);
        return version != null && version.getPackageArtifactRef() != null;
    }

    public String downloadUrl(Long pipelineId) {
        var version = pipelineMapper.selectById(pipelineId);
        if (version == null || version.getPackageArtifactRef() == null) throw invalid("算法包版本不存在");
        return fileApi.presignGetUrl(version.getPackageArtifactRef(), 600).getCheckedData();
    }

    public void validateTask(Map<String, Object> dag, Map<String, Object> parameters, Map<String, Long> bindings) {
        if (!(dag.get("algorithmPackage") instanceof Map<?, ?> descriptor)) return;
        var manifest = map(descriptor.get("manifest"));
        validateParameters(map(manifest.getOrDefault("parameterSchema", Map.of())), map(parameters.getOrDefault("algorithm", Map.of())));
        for (Object role : (List<?>) manifest.get("models")) {
            if (!bindings.containsKey(map(role).get("slot"))) throw invalid("算法缺少模型角色绑定");
        }
        resources(dag, parameters, bindings, false);
    }

    private Map<String, Object> result(PipelineVersionDO version, Map<String, Object> manifest, String digest) {
        return result(version, manifest, digest, algorithmMapper.selectById(version.getAlgorithmId()));
    }

    private Map<String, Object> result(PipelineVersionDO version, Map<String, Object> manifest, String digest, com.linsight.module.aivideo.dal.dataobject.algorithm.AlgorithmDO algorithm) {
        return Map.of("algorithmId", version.getAlgorithmId(), "pipelineVersionId", version.getId(),
                "manifest", manifest, "sha256", digest, "status", version.getValidationStatus(),
                "current", algorithm != null && Objects.equals(algorithm.getCurrentPipelineVersionId(), version.getId()));
    }
}
