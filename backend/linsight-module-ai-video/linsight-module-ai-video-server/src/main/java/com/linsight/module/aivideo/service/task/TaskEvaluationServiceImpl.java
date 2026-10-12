package com.linsight.module.aivideo.service.task;

import com.linsight.framework.common.pojo.PageResult;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.module.aivideo.controller.admin.task.vo.TaskEvaluationCreateReqVO;
import com.linsight.module.aivideo.controller.admin.task.vo.TaskEvaluationPageReqVO;
import com.linsight.module.aivideo.convert.task.TaskConvert;
import com.linsight.module.aivideo.dal.dataobject.task.TaskDO;
import com.linsight.module.aivideo.dal.dataobject.task.TaskEvaluationDO;
import com.linsight.module.aivideo.dal.mysql.task.TaskEvaluationMapper;
import com.linsight.module.aivideo.dal.mysql.task.TaskMapper;
import com.linsight.module.aivideo.service.algorithm.AlgorithmService;
import com.linsight.module.aivideo.service.model.ModelService;
import com.linsight.module.aivideo.service.node.NodeService;
import com.linsight.module.aivideo.service.rule.RuleService;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.*;

import static com.linsight.framework.common.exception.util.ServiceExceptionUtil.exception;
import static com.linsight.module.aivideo.enums.task.ErrorCodeConstants.*;

@Service
@Validated
public class TaskEvaluationServiceImpl implements TaskEvaluationService {
    @Resource private TaskEvaluationMapper evaluationMapper;
    @Resource private TaskMapper taskMapper;
    @Resource private AlgorithmService algorithmService;
    @Resource private ModelService modelService;
    @Resource private RuleService ruleService;
    @Resource private NodeService nodeService;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Long create(TaskEvaluationCreateReqVO request) {
        // Serialize retries and configuration changes through the existing task owner lock.
        var task = taskMapper.selectByIdForUpdate(request.getTaskId());
        if (task == null) throw exception(TASK_NOT_FOUND);
        String measurement = JsonUtils.toJsonString(request);
        String requestHash = sha256(measurement);
        var previous = evaluationMapper.selectByRequest(task.getId(), request.getRequestId());
        if (previous != null) {
            if (!Objects.equals(previous.getRequestHash(), requestHash)) {
                throw exception(TASK_EVALUATION_REQUEST_CONFLICT);
            }
            return previous.getId();
        }
        if (!Objects.equals(task.getConfigVersion(), request.getExpectedConfigVersion())) {
            throw exception(TASK_EVALUATION_CONFIG_CHANGED);
        }
        var runtime = JsonUtils.parseMap(task.getMetricsSnapshot());
        long gatewayRevision = runtime != null && runtime.get("gatewayRevision") instanceof Number revision
                ? revision.longValue() : 0;
        if (!Objects.equals(request.getExpectedGatewayRevision(), gatewayRevision)) {
            throw exception(TASK_EVALUATION_CONFIG_CHANGED);
        }
        if (request.getMeasuredAtMillis() > System.currentTimeMillis() + 60_000) {
            throw exception(TASK_EVALUATION_INVALID, "测试时间不能在未来");
        }
        String snapshot = JsonUtils.toJsonString(snapshot(task));
        if (snapshot.length() > 262_144 || measurement.length() > 16_384) {
            throw exception(TASK_EVALUATION_INVALID, "快照超过大小限制");
        }
        var failures = failedChecks(request);
        var record = new TaskEvaluationDO();
        record.setTaskId(task.getId());
        record.setTaskName(task.getName());
        record.setConfigVersion(task.getConfigVersion());
        record.setRequestId(request.getRequestId());
        record.setRequestHash(requestHash);
        record.setSource("MANUAL_VIDEO");
        record.setStatus(failures.isEmpty() ? "PASS" : "FAIL");
        record.setDatasetVersion(request.getDatasetVersion().trim());
        record.setDatasetSha256(request.getDatasetSha256().toLowerCase(Locale.ROOT));
        record.setMeasuredAtMillis(request.getMeasuredAtMillis());
        record.setEvidenceRef(request.getEvidenceRef());
        record.setMeasurement(measurement);
        record.setConfigurationSnapshot(snapshot);
        record.setFailedChecks(JsonUtils.toJsonString(failures));
        evaluationMapper.insert(record);
        return record.getId();
    }

    private Map<String, Object> snapshot(TaskDO task) {
        var result = new LinkedHashMap<String, Object>();
        result.put("schemaVersion", "1.0");
        result.put("capturedAtMillis", System.currentTimeMillis());
        result.put("configurationSource", "PLATFORM_TASK_AT_RECORDING");
        result.put("taskId", task.getId());
        result.put("configVersion", task.getConfigVersion());
        result.put("cameraId", task.getCameraId());
        result.put("recordedActiveRunId", task.getActiveRunId());
        result.put("parameters", JsonUtils.parseMap(task.getParameters()));
        result.put("globalSettingsVersion", task.getGlobalSettingsVersion());
        result.put("globalSettings", JsonUtils.parseMap(task.getGlobalSettingsSnapshot()));
        var bindings = TaskConvert.parseModelBindings(task.getModelBindings(), task.getModelVersionId());
        var gateway = TaskServiceImpl.reusableGatewayConfiguration(task);
        var runtime = JsonUtils.parseMap(task.getMetricsSnapshot());
        if (runtime != null && runtime.get("gatewayRevision") instanceof Number revision && revision.longValue() > 0) {
            // A central edit awaiting a gateway report is not the configuration just tested.
            if (gateway.isEmpty()) throw exception(TASK_EVALUATION_CONFIG_CHANGED);
            result.put("configurationSource", "GATEWAY_REPORTED_AT_RECORDING");
            result.put("gatewayRevision", revision);
            result.put("gatewayAppliedRevision", runtime.get("gatewayAppliedRevision"));
            var reported = new LinkedHashMap<String, Object>();
            for (String key : List.of("taskId", "cameraId", "algorithmId", "pipelineVersionId",
                    "configVersion", "modelVersionId", "modelBindings", "parameters", "ruleId", "ruleVersionId", "rule")) {
                if (gateway.containsKey(key)) reported.put(key, gateway.get(key));
            }
            result.put("gatewayConfiguration", reported);
            result.put("parameters", gateway.get("parameters"));
            Long primary = gateway.get("modelVersionId") instanceof Number value ? value.longValue() : task.getModelVersionId();
            bindings = TaskConvert.parseModelBindings(JsonUtils.toJsonString(gateway.get("modelBindings")), primary);
        }
        result.put("modelBindings", bindings);
        result.put("models", bindings.values().stream().distinct().sorted()
                .map(modelService::getEvaluationSnapshot).toList());
        result.put("pipeline", algorithmService.getEvaluationSnapshot(task.getAlgorithmId(), task.getPipelineVersionId()));
        result.put("rule", task.getRuleId() == null ? null
                : ruleService.getPublishedRuleConfig(task.getRuleId(), task.getRuleVersionId()));
        result.put("nodeAtRecording", nodeService.getEvaluationSnapshot(task.getNodeId()));
        return result;
    }

    static List<String> failedChecks(TaskEvaluationCreateReqVO request) {
        var measured = request.getMetrics();
        var thresholds = request.getThresholds();
        var failed = new ArrayList<String>();
        if (measured.getEventPrecision().compareTo(thresholds.getMinEventPrecision()) < 0) failed.add("eventPrecision");
        if (measured.getEventRecall().compareTo(thresholds.getMinEventRecall()) < 0) failed.add("eventRecall");
        if (measured.getFalsePositivesPerStreamHour().compareTo(thresholds.getMaxFalsePositivesPerStreamHour()) > 0) failed.add("falsePositivesPerStreamHour");
        if (measured.getMissedEvents() > thresholds.getMaxMissedEvents()) failed.add("missedEvents");
        if (measured.getEndToEndP95Ms().compareTo(thresholds.getMaxEndToEndP95Ms()) > 0) failed.add("endToEndP95Ms");
        if (measured.getAverageFps().compareTo(thresholds.getMinAverageFps()) < 0) failed.add("averageFps");
        if (!Boolean.TRUE.equals(request.getCooldownDedupPass())) failed.add("cooldownDedup");
        return failed;
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException("SHA-256 unavailable", error);
        }
    }

    @Override
    public TaskEvaluationDO get(Long id) {
        var record = evaluationMapper.selectById(id);
        if (record == null) throw exception(TASK_EVALUATION_NOT_FOUND);
        return record;
    }

    @Override
    public PageResult<TaskEvaluationDO> page(TaskEvaluationPageReqVO request) {
        return evaluationMapper.selectPage(request, request.getTaskId(), request.getStatus());
    }
}
