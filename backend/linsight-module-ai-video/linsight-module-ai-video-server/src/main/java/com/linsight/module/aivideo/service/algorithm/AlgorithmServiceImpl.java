package com.linsight.module.aivideo.service.algorithm;

import com.linsight.framework.common.pojo.PageResult;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.module.aivideo.controller.admin.algorithm.vo.AlgorithmPageReqVO;
import com.linsight.module.aivideo.controller.admin.algorithm.vo.AlgorithmSaveReqVO;
import com.linsight.module.aivideo.controller.admin.algorithm.vo.PipelineSaveReqVO;
import com.linsight.module.aivideo.dal.dataobject.algorithm.AlgorithmDO;
import com.linsight.module.aivideo.dal.dataobject.algorithm.PipelineVersionDO;
import com.linsight.module.aivideo.dal.mysql.algorithm.AlgorithmMapper;
import com.linsight.module.aivideo.dal.mysql.algorithm.PipelineVersionMapper;
import com.linsight.module.aivideo.service.model.ModelService;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

import static com.linsight.framework.common.exception.util.ServiceExceptionUtil.exception;
import static com.linsight.module.aivideo.enums.algorithm.ErrorCodeConstants.*;

@Service
public class AlgorithmServiceImpl implements AlgorithmService {
    @Override
    public List<AlgorithmSummaryDTO> getSummaries(java.util.Collection<Long> ids) {
        if (ids.isEmpty()) return List.of();
        return algorithmMapper.selectBatchIds(ids).stream()
                .map(value -> new AlgorithmSummaryDTO(value.getId(), value.getName(), value.getCapabilityKey(), value.getEventType()))
                .toList();
    }

    private static final Set<String> NODE_TYPES = Set.of(
            "DETECTOR", "TRACKER", "CLASSIFIER", "OCR", "RULE",
            "POSE", "SEGMENTER", "RECOGNIZER", "QUALITY");
    private static final java.util.regex.Pattern CAPABILITY_KEY_PATTERN =
            java.util.regex.Pattern.compile("^[a-z][a-z0-9.-]{1,63}$");

    @Resource private AlgorithmMapper algorithmMapper;
    @Resource private PipelineVersionMapper pipelineVersionMapper;
    @Resource private ModelService modelService;

    @Override
    public Long createAlgorithm(AlgorithmSaveReqVO reqVO) {
        if (algorithmMapper.selectByCode(reqVO.getCode()) != null) {
            throw exception(ALGORITHM_CODE_DUPLICATE);
        }
        validateJsonContract(reqVO.getParameterSchema(), reqVO.getDefaultParameters());
        if (reqVO.getDefaultModelId() != null) modelService.getModel(reqVO.getDefaultModelId());
        AlgorithmDO algorithm = toDO(reqVO);
        algorithmMapper.insert(algorithm);
        return algorithm.getId();
    }

    @Override
    public void updateAlgorithm(AlgorithmSaveReqVO reqVO) {
        AlgorithmDO existing = requireAlgorithm(reqVO.getId());
        if (!Objects.equals(existing.getCode(), reqVO.getCode())) {
            throw exception(ALGORITHM_CODE_IMMUTABLE);
        }
        validateJsonContract(reqVO.getParameterSchema(), reqVO.getDefaultParameters());
        if (reqVO.getDefaultModelId() != null) modelService.getModel(reqVO.getDefaultModelId());
        AlgorithmDO update = toDO(reqVO);
        algorithmMapper.updateById(update);
    }

    @Override
    public AlgorithmDO getAlgorithm(Long id) {
        return requireAlgorithm(id);
    }

    @Override
    public PageResult<AlgorithmDO> getAlgorithmPage(AlgorithmPageReqVO reqVO) {
        return algorithmMapper.selectPage(reqVO, reqVO.getName(), reqVO.getCode(),
                reqVO.getCategory(), reqVO.getSceneGroup(), reqVO.getImplementationType(), reqVO.getStatus());
    }

    @Override
    public List<AlgorithmDO> getRunnableAlgorithms() {
        return algorithmMapper.selectEnabledList();
    }

    @Override
    public Map<Long, List<AlgorithmCapabilityDTO>> getModelCapabilities() {
        List<AlgorithmDO> algorithms = getRunnableAlgorithms();
        Map<Long, PipelineVersionDO> pipelines = currentPipelines(algorithms);
        Map<Long, List<AlgorithmCapabilityDTO>> capabilitiesByModelId = new LinkedHashMap<>();
        for (AlgorithmDO algorithm : algorithms) {
            Set<Long> modelIds = new java.util.LinkedHashSet<>();
            if (algorithm.getDefaultModelId() != null) modelIds.add(algorithm.getDefaultModelId());
            PipelineVersionDO pipeline = pipelines.get(algorithm.getCurrentPipelineVersionId());
            String status = "UNPUBLISHED";
            if (pipeline != null && "PUBLISHED".equals(pipeline.getValidationStatus())) {
                Map<String, Object> dag = JsonUtils.parseMap(pipeline.getDag());
                status = acceptanceStatus(dag);
                if (dag.get("nodes") instanceof List<?> nodes) {
                    for (Object value : nodes) {
                        if (value instanceof Map<?, ?> node) {
                            if (node.get("modelId") instanceof Number modelId) {
                                modelIds.add(modelId.longValue());
                            }
                            if (node.get("modelIds") instanceof List<?> alternatives) {
                                alternatives.stream().filter(Number.class::isInstance)
                                        .map(Number.class::cast).map(Number::longValue)
                                        .forEach(modelIds::add);
                            }
                        }
                    }
                }
            }
            for (Long modelId : modelIds) {
                AlgorithmCapabilityDTO capability = new AlgorithmCapabilityDTO(
                        algorithm.getId(), modelId, algorithm.getName(), algorithm.getCode(),
                        algorithm.getCapabilityKey(), algorithm.getSceneGroup(), status);
                capabilitiesByModelId.computeIfAbsent(modelId, ignored -> new ArrayList<>()).add(capability);
            }
        }
        return capabilitiesByModelId;
    }

    @Override
    public Long savePipeline(PipelineSaveReqVO reqVO) {
        if (reqVO.getDag().containsKey("algorithmPackage")) throw AlgorithmPackageValidator.invalid("包版本须通过上传算法包创建，不能修改其描述或哈希");
        requireAlgorithm(reqVO.getAlgorithmId());
        List<String> errors = validateDag(reqVO.getDag());
        PipelineVersionDO latest = pipelineVersionMapper.selectLatestByAlgorithm(reqVO.getAlgorithmId());
        PipelineVersionDO version = new PipelineVersionDO();
        version.setAlgorithmId(reqVO.getAlgorithmId());
        version.setVersion(latest == null ? 1 : latest.getVersion() + 1);
        version.setDag(JsonUtils.toJsonString(reqVO.getDag()));
        version.setValidationStatus(errors.isEmpty() ? "VALID" : "DRAFT");
        version.setValidationErrors(errors.isEmpty() ? null : JsonUtils.toJsonString(errors));
        pipelineVersionMapper.insert(version);
        return version.getId();
    }

    @Override
    public List<String> validatePipeline(Long id) {
        PipelineVersionDO pipeline = requirePipeline(id);
        List<String> errors = validateDag(JsonUtils.parseMap(pipeline.getDag()));
        pipeline.setValidationStatus(errors.isEmpty() ? "VALID" : "DRAFT");
        pipeline.setValidationErrors(errors.isEmpty() ? null : JsonUtils.toJsonString(errors));
        pipelineVersionMapper.updateById(pipeline);
        return errors;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void publishPipeline(Long id) {
        PipelineVersionDO pipeline = requirePipeline(id);
        if (JsonUtils.parseMap(pipeline.getDag()).containsKey("algorithmPackage") && pipeline.getPackageArtifactRef() == null) {
            throw AlgorithmPackageValidator.invalid("算法包没有经过上传校验");
        }
        List<String> errors = validateDag(JsonUtils.parseMap(pipeline.getDag()));
        if (!errors.isEmpty()) throw exception(PIPELINE_INVALID);
        pipeline.setValidationStatus("PUBLISHED");
        pipeline.setValidationErrors(null);
        pipeline.setPublishedTime(LocalDateTime.now());
        pipelineVersionMapper.updateById(pipeline);
        AlgorithmDO algorithm = requireAlgorithm(pipeline.getAlgorithmId());
        algorithm.setCurrentPipelineVersionId(pipeline.getId());
        if (JsonUtils.parseMap(pipeline.getDag()).get("algorithmPackage") instanceof Map<?, ?> descriptor
                && descriptor.get("manifest") instanceof Map<?, ?> manifest) {
            algorithm.setEventType(String.valueOf(manifest.containsKey("eventType") ? manifest.get("eventType") : "ALGORITHM_EVENT"));
        }
        algorithmMapper.updateById(algorithm);
    }

    @Override
    public List<PipelineVersionDO> getPipelineVersions(Long algorithmId) {
        requireAlgorithm(algorithmId);
        return pipelineVersionMapper.selectListByAlgorithm(algorithmId);
    }

    @Override
    public PipelineVersionDO getPublishedPipeline(Long algorithmId, Long pipelineVersionId) {
        AlgorithmDO algorithm = requireAlgorithm(algorithmId);
        Long selectedId = pipelineVersionId == null ? algorithm.getCurrentPipelineVersionId() : pipelineVersionId;
        PipelineVersionDO pipeline = requirePipeline(selectedId);
        if (!Objects.equals(pipeline.getAlgorithmId(), algorithmId)
                || !"PUBLISHED".equals(pipeline.getValidationStatus())) {
            throw exception(PIPELINE_NOT_PUBLISHED);
        }
        return pipeline;
    }

    @Override
    public AlgorithmEvaluationSnapshotDTO getEvaluationSnapshot(Long algorithmId, Long pipelineVersionId) {
        if (pipelineVersionId == null) throw exception(PIPELINE_NOT_PUBLISHED);
        var pipeline = getPublishedPipeline(algorithmId, pipelineVersionId);
        return new AlgorithmEvaluationSnapshotDTO(algorithmId, pipeline.getId(), pipeline.getVersion(),
                JsonUtils.parseMap(pipeline.getDag()));
    }

    @Override
    public String getPipelineAcceptanceStatus(Long algorithmId) {
        AlgorithmDO algorithm = requireAlgorithm(algorithmId);
        return getPipelineAcceptanceStatuses(List.of(algorithm)).get(algorithmId);
    }

    @Override
    public Map<Long, String> getPipelineAcceptanceStatuses(List<AlgorithmDO> algorithms) {
        if (algorithms == null || algorithms.isEmpty()) return Map.of();
        Map<Long, PipelineVersionDO> pipelines = currentPipelines(algorithms);
        Map<Long, String> statuses = new LinkedHashMap<>();
        for (AlgorithmDO algorithm : algorithms) {
            PipelineVersionDO pipeline = pipelines.get(algorithm.getCurrentPipelineVersionId());
            String status = pipeline == null || !"PUBLISHED".equals(pipeline.getValidationStatus())
                    ? "UNPUBLISHED"
                    : acceptanceStatus(JsonUtils.parseMap(pipeline.getDag()));
            statuses.put(algorithm.getId(), status);
        }
        return statuses;
    }

    private Map<Long, PipelineVersionDO> currentPipelines(List<AlgorithmDO> algorithms) {
        List<Long> pipelineIds = algorithms.stream()
                .map(AlgorithmDO::getCurrentPipelineVersionId)
                .filter(Objects::nonNull)
                .distinct()
                .toList();
        Map<Long, PipelineVersionDO> pipelines = new HashMap<>();
        if (!pipelineIds.isEmpty()) {
            pipelineVersionMapper.selectBatchIds(pipelineIds)
                    .forEach(pipeline -> pipelines.put(pipeline.getId(), pipeline));
        }
        return pipelines;
    }

    @Override
    public void validatePipelineRunnable(PipelineVersionDO pipeline) {
        validatePipelineRunnable(pipeline, false);
    }

    @Override
    public void validatePipelineRunnable(PipelineVersionDO pipeline, boolean validationOnly) {
        String status = acceptanceStatus(JsonUtils.parseMap(pipeline.getDag()));
        if (validationOnly && ("PENDING".equals(status) || "BLOCKED_EXTERNAL_ASSETS".equals(status))) return;
        if (!"PASS".equals(status)) throw exception(PIPELINE_ACCEPTANCE_BLOCKED, status);
    }

    private AlgorithmDO requireAlgorithm(Long id) {
        AlgorithmDO algorithm = id == null ? null : algorithmMapper.selectById(id);
        if (algorithm == null) throw exception(ALGORITHM_NOT_FOUND);
        return algorithm;
    }

    private PipelineVersionDO requirePipeline(Long id) {
        PipelineVersionDO pipeline = id == null ? null : pipelineVersionMapper.selectById(id);
        if (pipeline == null) throw exception(PIPELINE_NOT_FOUND);
        return pipeline;
    }

    private static AlgorithmDO toDO(AlgorithmSaveReqVO reqVO) {
        AlgorithmDO algorithm = new AlgorithmDO();
        algorithm.setId(reqVO.getId());
        algorithm.setName(reqVO.getName());
        algorithm.setCode(reqVO.getCode());
        algorithm.setCategory(reqVO.getCategory());
        algorithm.setSceneGroup(reqVO.getSceneGroup());
        algorithm.setImplementationType(reqVO.getImplementationType());
        algorithm.setDescription(reqVO.getDescription());
        algorithm.setCapabilityKey(reqVO.getCapabilityKey());
        algorithm.setRequiredCapabilities(JsonUtils.toJsonString(reqVO.getRequiredCapabilities().isEmpty()
                ? List.of(reqVO.getCapabilityKey()) : reqVO.getRequiredCapabilities()));
        algorithm.setEventType(reqVO.getEventType());
        algorithm.setDefaultModelId(reqVO.getDefaultModelId());
        algorithm.setParameterSchema(JsonUtils.toJsonString(reqVO.getParameterSchema()));
        algorithm.setDefaultParameters(JsonUtils.toJsonString(reqVO.getDefaultParameters()));
        algorithm.setStatus(reqVO.getStatus());
        return algorithm;
    }

    private static void validateJsonContract(Map<String, Object> schema, Map<String, Object> defaults) {
        if (!"1.0".equals(schema.get("schemaVersion")) || !"1.0".equals(defaults.get("schemaVersion"))) {
            throw exception(PIPELINE_INVALID);
        }
    }

    static List<String> validateDag(Map<String, Object> dag) {
        List<String> errors = new ArrayList<>();
        if (dag == null || !"1.0".equals(dag.get("schemaVersion"))) {
            return List.of("schemaVersion 必须为 1.0");
        }
        if (!(dag.get("nodes") instanceof List<?> nodes) || nodes.isEmpty()) {
            return List.of("Pipeline 至少包含一个受控节点");
        }
        Map<String, Set<String>> graph = new HashMap<>();
        Map<String, Integer> indegree = new HashMap<>();
        Map<String, String> capabilities = new HashMap<>();
        for (Object value : nodes) {
            if (!(value instanceof Map<?, ?> node) || !(node.get("id") instanceof String id)
                    || id.isBlank() || !(node.get("type") instanceof String type)
                    || !NODE_TYPES.contains(type) || !(node.get("capabilityKey") instanceof String capability)
                    || !CAPABILITY_KEY_PATTERN.matcher(capability).matches()) {
                errors.add("节点必须包含唯一 id、受控 type 和 capabilityKey");
                continue;
            }
            if (graph.putIfAbsent(id, new HashSet<>()) != null) errors.add("节点 id 重复：" + id);
            indegree.putIfAbsent(id, 0);
            capabilities.put(id, capability);
            if (node.get("modelIds") != null) {
                if (!(node.get("modelIds") instanceof List<?> modelIds) || modelIds.isEmpty()
                        || modelIds.size() > 32 || modelIds.stream().anyMatch(modelId -> !positiveId(modelId))) {
                    errors.add("节点 modelIds 必须包含 1 至 32 个有效模型编号");
                } else if (node.get("modelId") instanceof Number modelId
                        && modelIds.stream().filter(Number.class::isInstance).map(Number.class::cast)
                                .noneMatch(valueId -> valueId.longValue() == modelId.longValue())) {
                    errors.add("节点 modelId 必须包含在 modelIds 中");
                }
            }
        }
        Object edgesValue = dag.get("edges");
        if (edgesValue != null && !(edgesValue instanceof List<?>)) errors.add("edges 必须是数组");
        if (edgesValue instanceof List<?> edges) {
            for (Object value : edges) {
                if (!(value instanceof Map<?, ?> edge) || !(edge.get("from") instanceof String from)
                        || !(edge.get("to") instanceof String to) || !graph.containsKey(from)
                        || !graph.containsKey(to)) {
                    errors.add("边引用了不存在的节点");
                    continue;
                }
                if (graph.get(from).add(to)) indegree.compute(to, (key, degree) -> degree == null ? 1 : degree + 1);
            }
        }
        ArrayDeque<String> queue = new ArrayDeque<>();
        indegree.forEach((id, degree) -> { if (degree == 0) queue.add(id); });
        int visited = 0;
        while (!queue.isEmpty()) {
            String current = queue.remove();
            visited++;
            for (String next : graph.getOrDefault(current, Set.of())) {
                int degree = indegree.computeIfPresent(next, (key, value) -> value - 1);
                if (degree == 0) queue.add(next);
            }
        }
        if (visited != graph.size()) errors.add("Pipeline DAG 存在循环依赖");
        Set<String> pairs = new HashSet<>();
        graph.forEach((from, targets) -> targets.forEach(to -> pairs.add(
                capabilities.get(from) + "->" + capabilities.get(to))));
        Set<String> values = new HashSet<>(capabilities.values());
        requireChain(values, pairs, errors, "ppe.helmet",
                "detector.person->ppe.helmet", "ppe.helmet->tracker.iou");
        requireChain(values, pairs, errors, "ppe.reflective-vest",
                "detector.person->ppe.reflective-vest", "ppe.reflective-vest->tracker.iou");
        requireChain(values, pairs, errors, "behavior.smoking", "behavior.smoking->tracker.iou");
        requireChain(values, pairs, errors, "behavior.phone-call", "behavior.phone-call->tracker.iou");
        requireChain(values, pairs, errors, "behavior.fall", "behavior.fall->tracker.iou");
        requireChain(values, pairs, errors, "detector.vehicle", "detector.vehicle->tracker.iou");
        requireChain(values, pairs, errors, "ocr.license-plate",
                "detector.license-plate->ocr.license-plate", "ocr.license-plate->tracker.iou");
        requireChain(values, pairs, errors, "rule.person-intrusion",
                "detector.person->tracker.iou", "tracker.iou->rule.person-intrusion");
        requireChain(values, pairs, errors, "rule.area-intrusion",
                "detector.person->tracker.iou", "tracker.iou->rule.area-intrusion");
        requireChain(values, pairs, errors, "rule.person-absence",
                "detector.person->tracker.iou", "tracker.iou->rule.person-absence");
        requireChain(values, pairs, errors, "rule.roi",
                requiredDetector(values) + "->tracker.iou", "tracker.iou->rule.roi");
        requireChain(values, pairs, errors, "rule.count",
                requiredDetector(values) + "->tracker.iou", "tracker.iou->rule.count");
        requireChain(values, pairs, errors, "rule.line-crossing",
                requiredDetector(values) + "->tracker.iou", "tracker.iou->rule.line-crossing");
        requireChain(values, pairs, errors, "rule.direction",
                requiredDetector(values) + "->tracker.iou", "tracker.iou->rule.direction");
        requireChain(values, pairs, errors, "rule.stationary",
                requiredDetector(values) + "->tracker.iou", "tracker.iou->rule.stationary");
        requireChain(values, pairs, errors, "rule.distance",
                requiredDetector(values) + "->tracker.iou", "tracker.iou->rule.distance");
        Object acceptance = dag.get("acceptance");
        if (acceptance != null) {
            if (!(acceptance instanceof Map<?, ?> value)
                    || !(value.get("status") instanceof String status)
                    || !("PASS".equals(status) || "PENDING".equals(status) || status.startsWith("BLOCKED_"))) {
                errors.add("acceptance.status 必须为 PASS、PENDING 或 BLOCKED_* 状态");
            } else if ("VIDEO_ACCEPTANCE".equals(value.get("source"))) {
                validateVideoAcceptance(value, errors);
            }
        }
        return errors;
    }

    private static void validateVideoAcceptance(Map<?, ?> acceptance, List<String> errors) {
        if (!(acceptance.get("taskId") instanceof Number taskId) || taskId.longValue() <= 0) {
            errors.add("视频验收必须绑定有效任务");
        }
        if (!(acceptance.get("datasetVersion") instanceof String datasetVersion) || datasetVersion.isBlank()
                || !(acceptance.get("datasetSha256") instanceof String datasetSha256)
                || !datasetSha256.matches("^[a-fA-F0-9]{64}$")
                || !(acceptance.get("evidenceRef") instanceof String evidenceRef) || evidenceRef.isBlank()) {
            errors.add("视频验收必须填写固定测试集版本、SHA256 和证据引用");
        }
        if (!(acceptance.get("metrics") instanceof Map<?, ?> metrics)
                || !(acceptance.get("thresholds") instanceof Map<?, ?> thresholds)) {
            errors.add("视频验收必须包含指标和阈值");
            return;
        }
        if (!between(metrics.get("eventPrecision"), 0, 1)
                || !between(metrics.get("eventRecall"), 0, 1)
                || !atLeast(metrics.get("falsePositivesPerStreamHour"), 0)
                || !nonNegativeInteger(metrics.get("missedEvents"))
                || !between(metrics.get("endToEndP95Ms"), 0, 1999.999)
                || !atLeast(metrics.get("averageFps"), Double.MIN_VALUE)
                || !between(thresholds.get("minEventPrecision"), 0, 1)
                || !between(thresholds.get("minEventRecall"), 0, 1)
                || !atLeast(thresholds.get("maxFalsePositivesPerStreamHour"), 0)
                || !nonNegativeInteger(thresholds.get("maxMissedEvents"))
                || !between(thresholds.get("maxEndToEndP95Ms"), Double.MIN_VALUE, 1999.999)
                || !atLeast(thresholds.get("minAverageFps"), Double.MIN_VALUE)) {
            errors.add("视频验收指标或阈值超出允许范围");
        }
        if (!(acceptance.get("resourceUsage") instanceof Map<?, ?> resources)
                || !between(resources.get("cpuPeakPercent"), 0, 100)
                || !atLeast(resources.get("memoryPeakMiB"), Double.MIN_VALUE)
                || !atLeast(resources.get("acceleratorMemoryPeakMiB"), 0)) {
            errors.add("视频验收必须包含有效的 CPU、内存和加速器显存峰值");
        }
        boolean pass = compare(metrics, thresholds, "eventPrecision", "minEventPrecision", true)
                && compare(metrics, thresholds, "eventRecall", "minEventRecall", true)
                && compare(metrics, thresholds, "falsePositivesPerStreamHour", "maxFalsePositivesPerStreamHour", false)
                && compare(metrics, thresholds, "missedEvents", "maxMissedEvents", false)
                && compare(metrics, thresholds, "endToEndP95Ms", "maxEndToEndP95Ms", false)
                && compare(metrics, thresholds, "averageFps", "minAverageFps", true)
                && Boolean.TRUE.equals(acceptance.get("cooldownDedupPass"));
        if ("PASS".equals(acceptance.get("status")) && !pass) {
            errors.add("视频验收指标未达到阈值，不能标记为 PASS");
        }
    }

    private static boolean compare(Map<?, ?> metrics, Map<?, ?> thresholds,
                                   String metricName, String thresholdName, boolean atLeast) {
        if (!(metrics.get(metricName) instanceof Number metric)
                || !(thresholds.get(thresholdName) instanceof Number threshold)) return false;
        double actual = metric.doubleValue();
        double target = threshold.doubleValue();
        return Double.isFinite(actual) && Double.isFinite(target)
                && (atLeast ? actual >= target : actual <= target);
    }

    private static boolean between(Object value, double minimum, double maximum) {
        return value instanceof Number number && Double.isFinite(number.doubleValue())
                && number.doubleValue() >= minimum && number.doubleValue() <= maximum;
    }

    private static boolean atLeast(Object value, double minimum) {
        return value instanceof Number number && Double.isFinite(number.doubleValue())
                && number.doubleValue() >= minimum;
    }

    private static boolean nonNegativeInteger(Object value) {
        return value instanceof Number number && Double.isFinite(number.doubleValue())
                && number.doubleValue() >= 0 && number.doubleValue() == Math.rint(number.doubleValue());
    }

    private static boolean positiveId(Object value) {
        return value instanceof Number number && Double.isFinite(number.doubleValue())
                && number.longValue() > 0 && number.doubleValue() == number.longValue();
    }

    static String acceptanceStatus(Map<String, Object> dag) {
        Object acceptance = dag.get("acceptance");
        if (acceptance == null) return "PASS";
        if (!(acceptance instanceof Map<?, ?> value) || !(value.get("status") instanceof String status)
                || status.isBlank()) return "INVALID";
        return status;
    }

    private static void requireChain(Set<String> capabilities, Set<String> pairs, List<String> errors,
                                     String capability, String... requiredPairs) {
        if (!capabilities.contains(capability)) return;
        for (String pair : requiredPairs) {
            if (!pairs.contains(pair)) {
                errors.add(capability + " 缺少受控链路：" + pair);
            }
        }
    }

    private static String requiredDetector(Set<String> capabilities) {
        return capabilities.stream()
                .filter(capability -> capability.startsWith("detector."))
                .findFirst()
                .orElse("detector.coco");
    }
}
