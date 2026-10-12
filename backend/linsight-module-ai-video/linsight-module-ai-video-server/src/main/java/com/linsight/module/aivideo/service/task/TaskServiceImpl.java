package com.linsight.module.aivideo.service.task;

import com.linsight.framework.common.pojo.PageResult;
import com.linsight.framework.common.exception.ServiceException;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.module.aivideo.controller.admin.task.vo.TaskPageReqVO;
import com.linsight.module.aivideo.controller.admin.task.vo.TaskSaveReqVO;
import com.linsight.module.aivideo.controller.admin.task.vo.TaskRuleUpdateReqVO;
import com.linsight.module.aivideo.controller.admin.task.vo.TaskBatchCreateReqVO;
import com.linsight.module.aivideo.controller.admin.task.vo.TaskBatchResultRespVO;
import com.linsight.module.aivideo.controller.node.task.vo.TaskCommandDetailRespVO;
import com.linsight.module.aivideo.controller.node.task.vo.TaskRuntimeReportReqVO;
import com.linsight.module.aivideo.controller.node.task.vo.TaskRemovalReportReqVO;
import com.linsight.module.aivideo.convert.task.TaskConvert;
import com.linsight.module.aivideo.dal.dataobject.algorithm.AlgorithmDO;
import com.linsight.module.aivideo.dal.dataobject.algorithm.PipelineVersionDO;
import com.linsight.module.aivideo.dal.dataobject.camera.CameraDO;
import com.linsight.module.aivideo.dal.dataobject.model.ModelVersionDO;
import com.linsight.module.aivideo.dal.dataobject.task.TaskDO;
import com.linsight.module.aivideo.dal.dataobject.task.TaskRunDO;
import com.linsight.module.aivideo.dal.mysql.task.TaskMapper;
import com.linsight.module.aivideo.dal.mysql.task.TaskRunMapper;
import com.linsight.module.aivideo.service.algorithm.AlgorithmService;
import com.linsight.module.aivideo.service.camera.CameraService;
import com.linsight.module.aivideo.service.model.ModelExecutionService;
import com.linsight.module.aivideo.service.model.ModelService;
import com.linsight.module.aivideo.service.node.NodeCommandDTO;
import com.linsight.module.aivideo.service.node.NodeCommandService;
import com.linsight.module.aivideo.service.node.NodeService;
import com.linsight.module.aivideo.service.rule.RuleService;
import com.linsight.module.aivideo.service.rule.RuleVersionConfigDTO;
import com.linsight.module.aivideo.service.rule.RuleAstValidator;
import com.linsight.module.aivideo.service.rule.RuleRegionGeometryDTO;
import com.linsight.module.aivideo.service.settings.GlobalSettingsService;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;
import org.springframework.beans.BeanUtils;
import org.springframework.dao.DuplicateKeyException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;
import java.util.Locale;

import static com.linsight.framework.common.exception.util.ServiceExceptionUtil.exception;
import static com.linsight.module.aivideo.enums.task.ErrorCodeConstants.*;

@Service
public class TaskServiceImpl implements TaskService {
    private static final Logger log = LoggerFactory.getLogger(TaskServiceImpl.class);
    @Override
    public java.util.Map<Long, String> getTaskNames(java.util.Collection<Long> ids) {
        if (ids == null || ids.isEmpty()) return java.util.Map.of();
        return taskMapper.selectByIds(ids).stream().collect(java.util.stream.Collectors.toMap(
                TaskDO::getId, TaskDO::getName));
    }

    @Override
    public List<TaskCameraCapabilityDTO> getCameraCapabilities(java.util.Collection<Long> cameraIds) {
        if (cameraIds.isEmpty()) return List.of();
        return taskMapper.selectList(new com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX<TaskDO>()
                .in(TaskDO::getCameraId, cameraIds).orderByDesc(TaskDO::getId)).stream().map(task -> {
            var parameters = JsonUtils.parseTree(task.getParameters() == null ? "{}" : task.getParameters());
            var metrics = JsonUtils.parseTree(task.getMetricsSnapshot() == null ? "{}" : task.getMetricsSnapshot());
            return new TaskCameraCapabilityDTO(task.getId(), task.getName(), task.getCameraId(),
                    task.getAlgorithmId(), task.getNodeId(), task.getActualStatus(), task.getDesiredStatus(),
                    task.getActiveRunId(), task.getLastHeartbeatTime(),
                    parameters.path("validationOnly").isBoolean() && parameters.path("validationOnly").asBoolean(),
                    parameters.path("sampleFps").isNumber() ? parameters.path("sampleFps").asDouble() : null,
                    metrics.path("analysisFps").isNumber() ? metrics.path("analysisFps").asDouble() : null,
                    metrics.path("totalLatencyMillis").isNumber() ? metrics.path("totalLatencyMillis").asDouble() : null,
                    metrics.path("executionBackend").asText(null), task.getErrorCode(), task.getErrorMessage(),
                    appliedRegions(task, metrics));
        }).toList();
    }

    private static List<RuleRegionGeometryDTO> appliedRegions(TaskDO task, com.fasterxml.jackson.databind.JsonNode metrics) {
        var configuration = metrics.path("gatewayConfiguration");
        long revision = metrics.path("gatewayRevision").asLong(0);
        if (revision <= 0 || metrics.path("gatewayAppliedRevision").asLong(0) != revision
                || !Objects.equals(task.getId(), configuration.path("taskId").asLong(-1))
                || !Objects.equals(task.getCameraId(), configuration.path("cameraId").asLong(-1))) return List.of();
        // A published template is not evidence of the region actually applied on the device.
        return RuleRegionGeometryDTO.fromRule(configuration.path("rule"));
    }

    @Override
    public java.util.Map<Long, Long> getNodeCounts(java.util.Collection<Long> nodeIds) {
        if (nodeIds.isEmpty()) return java.util.Map.of();
        var query = new com.baomidou.mybatisplus.core.conditions.query.QueryWrapper<TaskDO>()
                .select("node_id", "COUNT(*) AS node_count").in("node_id", nodeIds).groupBy("node_id");
        
        java.util.Map<Long, Long> result = new java.util.HashMap<>();
        for (var row : taskMapper.selectMaps(query)) {
            result.put(((Number) row.get("node_id")).longValue(), ((Number) row.get("node_count")).longValue());
        }
        return result;
    }
    @Resource private TaskMapper taskMapper;
    @Resource private TaskRunMapper taskRunMapper;
    @Resource private CameraService cameraService;
    @Resource private AlgorithmService algorithmService;
    @Resource private com.linsight.module.aivideo.service.algorithm.AlgorithmPackageService algorithmPackageService;
    @Resource private ModelService modelService;
    @Resource private ModelExecutionService modelExecutionService;
    @Resource private NodeService nodeService;
    @Resource private NodeCommandService nodeCommandService;
    @Resource private RuleService ruleService;
    @Resource private TransactionTemplate transactionTemplate;
    @Resource private GlobalSettingsService globalSettingsService;

    @Override
    public Long createTask(TaskSaveReqVO reqVO) {
        if (taskMapper.selectByCode(reqVO.getCode()) != null) throw exception(TASK_CODE_DUPLICATE);
        PipelineVersionDO pipeline = validateConfig(reqVO, false);
        validateConfirmationLatency(reqVO.getParameters(), reqVO.getRuleId(), reqVO.getRuleVersionId());
        TaskDO task = toTask(reqVO, pipeline.getId());
        task.setDesiredStatus("STOPPED");
        task.setActualStatus("DRAFT");
        task.setConfigVersion(1);
        var globalSettings = globalSettingsService.getCurrent();
        task.setGlobalSettingsVersion(globalSettings.getVersionNo());
        task.setAppliedGlobalSettingsVersion(0);
        task.setGlobalSettingsSnapshot(JsonUtils.toJsonString(globalSettings.getSettings()));
        task.setVersion(1);
        taskMapper.insert(task);
        return task.getId();
    }

    @Override
    public List<TaskBatchResultRespVO> batchCreateTasks(TaskBatchCreateReqVO reqVO) {
        // Do not wrap the batch in a transaction: one failed camera must not undo others.
        return reqVO.getCameraIds().stream().distinct().map(cameraId -> {
            String code = "cam-" + cameraId + "-" + reqVO.getRequestId().replace("-", "").toLowerCase(java.util.Locale.ROOT);
            try {
                TaskDO replay = taskMapper.selectByCode(code);
                if (replay != null) return batchReplay(cameraId, reqVO.getAlgorithmId(), replay);
                if (taskMapper.countDeletedByCode(code) > 0) {
                    return new TaskBatchResultRespVO(cameraId, null, "FAILED", null, TASK_STATUS_INVALID.getCode(),
                            "本次配置已被移除，请重新发起配置");
                }
                List<TaskDO> existing = taskMapper.selectByCameraAndAlgorithm(cameraId, reqVO.getAlgorithmId());
                if (!existing.isEmpty()) {
                    TaskDO first = existing.get(0);
                    return new TaskBatchResultRespVO(cameraId, first.getId(), "UNCHANGED", first.getActualStatus(),
                            null, "已配置该算法，保留原设置和运行状态");
                }
                if (reqVO.getRuleId() != null && reqVO.getRuleVersionId() != null && !reqVO.isConfirmSharedRegions()) {
                    if (ruleService.getPublishedRuleConfig(reqVO.getRuleId(), reqVO.getRuleVersionId()).hasCustomRegions()) {
                        return new TaskBatchResultRespVO(cameraId, null, "FAILED", null, TASK_CONFIG_INVALID.getCode(),
                                "告警规则包含画面区域，请确认区域适用于所选摄像头后再保存");
                    }
                }
                TaskSaveReqVO draft = new TaskSaveReqVO();
                BeanUtils.copyProperties(reqVO, draft);
                draft.setCameraId(cameraId);
                draft.setCode(code);
                String cameraName = cameraService.getCameraNames(List.of(cameraId)).getOrDefault(cameraId, "摄像头 " + cameraId);
                String algorithmName = algorithmService.getSummaries(List.of(reqVO.getAlgorithmId())).stream()
                        .findFirst().map(item -> item.name()).orElse("算法 " + reqVO.getAlgorithmId());
                String name = cameraName + " · " + algorithmName;
                draft.setName(name.substring(0, Math.min(100, name.length())));
                Long id = createTask(draft);
                return new TaskBatchResultRespVO(cameraId, id, "CREATED", "DRAFT", null, "配置已保存，尚未启动");
            } catch (DuplicateKeyException exception) {
                TaskDO replay = taskMapper.selectByCode(code);
                if (replay != null) return batchReplay(cameraId, reqVO.getAlgorithmId(), replay);
                return new TaskBatchResultRespVO(cameraId, null, "FAILED", null, TASK_CODE_DUPLICATE.getCode(),
                        "本次配置已被移除，请重新发起配置");
            } catch (ServiceException exception) {
                return new TaskBatchResultRespVO(cameraId, null, "FAILED", null, exception.getCode(), exception.getMessage());
            } catch (RuntimeException exception) {
                log.error("Camera algorithm assignment failed for camera {}", cameraId, exception);
                return new TaskBatchResultRespVO(cameraId, null, "FAILED", null, TASK_CONFIG_INVALID.getCode(),
                        "保存失败，请重试；已保存的摄像头不会重复创建");
            }
        }).toList();
    }

    private TaskBatchResultRespVO batchReplay(Long cameraId, Long algorithmId, TaskDO task) {
        if (!Objects.equals(task.getCameraId(), cameraId) || !Objects.equals(task.getAlgorithmId(), algorithmId)) {
            return new TaskBatchResultRespVO(cameraId, null, "FAILED", null, TASK_CONFIG_INVALID.getCode(), "请求标识已用于其他配置，请重新发起");
        }
        return new TaskBatchResultRespVO(cameraId, task.getId(), "CREATED", task.getActualStatus(), null, "本次配置已保存，未重复创建");
    }

    @Override
    public void updateTask(TaskSaveReqVO reqVO) {
        TaskDO existing = requireTask(reqVO.getId());
        if (!Set.of("DRAFT", "STOPPED").contains(existing.getActualStatus())) throw exception(TASK_STATUS_INVALID);
        if (!Objects.equals(existing.getCode(), reqVO.getCode())) throw exception(TASK_CODE_IMMUTABLE);
        PipelineVersionDO pipeline = validateConfig(reqVO, false);
        if (confirmationConfigurationChanged(existing, reqVO)) {
            validateConfirmationLatency(reqVO.getParameters(), reqVO.getRuleId(), reqVO.getRuleVersionId());
        }
        TaskDO update = toTask(reqVO, pipeline.getId());
        update.setConfigVersion(existing.getConfigVersion() + 1);
        taskMapper.updateById(update);
    }

    @Override
    public void updateTaskRule(TaskRuleUpdateReqVO reqVO) {
        TaskDO task = requireTask(reqVO.getId());
        if (!Set.of("DRAFT", "STOPPED").contains(task.getActualStatus())
                || !"STOPPED".equals(task.getDesiredStatus())) throw exception(TASK_STATUS_INVALID);
        var rule = ruleService.getPublishedRuleConfig(reqVO.getRuleId(), reqVO.getRuleVersionId());
        var algorithm = algorithmService.getSummaries(List.of(task.getAlgorithmId())).stream()
                .findFirst().orElseThrow(() -> exception(TASK_CONFIG_INVALID));
        if (!Objects.equals(algorithmPackageService.eventType(task.getPipelineVersionId(), algorithm.eventType()), rule.getEventType())) throw exception(TASK_CONFIG_INVALID);
        if (Objects.equals(task.getRuleId(), reqVO.getRuleId())
                && Objects.equals(task.getRuleVersionId(), reqVO.getRuleVersionId())
                && (Objects.equals(task.getConfigVersion(), reqVO.getExpectedConfigVersion())
                    || task.getConfigVersion() == reqVO.getExpectedConfigVersion() + 1)) return;
        validateConfirmationLatency(JsonUtils.parseMap(task.getParameters()), rule);
        if (taskMapper.updateRuleVersion(task.getId(), reqVO.getExpectedConfigVersion(),
                reqVO.getRuleId(), reqVO.getRuleVersionId()) != 1) throw exception(TASK_CONFIG_INVALID);
    }

    @Override
    public void deleteTask(Long id) {
        TaskDO task = requireTask(id);
        if (!Set.of("DRAFT", "STOPPED").contains(task.getActualStatus())) throw exception(TASK_STATUS_INVALID);
        if (gatewayRevision(task) > 0) {
            nodeService.removeGatewayTask(task.getNodeId(), id, gatewayRevision(task));
        }
        taskMapper.deleteById(id);
    }

    @Override
    public TaskDO getTask(Long id) {
        return requireTask(id);
    }

    @Override
    public PageResult<TaskDO> getTaskPage(TaskPageReqVO reqVO) {
        return taskMapper.selectPage(reqVO, reqVO.getName(), reqVO.getCode(), reqVO.getCameraId(),
                reqVO.getAlgorithmId(), reqVO.getNodeId(), reqVO.getActualStatus());
    }

    @Override
    public List<TaskRunDO> getRuns(Long taskId) {
        requireTask(taskId);
        return taskRunMapper.selectListByTask(taskId);
    }

    @Override
    public boolean hasTasksForNode(Long nodeId) {
        return taskMapper.existsByNodeId(nodeId);
    }

    @Override
    public String getActiveStreamType(Long cameraId, Long nodeId) {
        return activeCameraTasks(cameraId, nodeId).stream()
                .map(task -> streamType(executionConfiguration(task).getParameters()))
                .findFirst().orElse(null);
    }

    private List<TaskDO> activeCameraTasks(Long cameraId, Long nodeId) {
        return taskMapper.selectList(new com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX<TaskDO>()
                .eq(TaskDO::getCameraId, cameraId)
                .eq(TaskDO::getNodeId, nodeId)
                .in(TaskDO::getActualStatus, List.of("STARTING", "RUNNING")));
    }

    @Override
    public String startTask(Long id) {
        TaskDO validated = requireTask(id);
        if (!Set.of("DRAFT", "STOPPED", "FAILED", "OFFLINE").contains(validated.getActualStatus())) {
            throw exception(TASK_STATUS_INVALID);
        }
        TaskSaveReqVO configuration = executionConfiguration(validated);
        long validatedGatewayRevision = gatewayRevision(validated);
        validateConfig(configuration, true);
        String selectedStream = streamType(configuration.getParameters());
        if (activeCameraTasks(validated.getCameraId(), validated.getNodeId()).stream()
                .filter(other -> !Objects.equals(other.getId(), id))
                .anyMatch(other -> !Objects.equals(selectedStream,
                        streamType(executionConfiguration(other).getParameters())))) {
            throw exception(TASK_STREAM_CONFLICT);
        }
        // Resolve here so a missing camera URL fails before a START_TASK command is queued.
        cameraService.getRuntimeStreamUrl(validated.getCameraId(), selectedStream);
        var capacity = nodeService.preflightTaskCapacity(validated.getNodeId(), validated.getId(),
                normalizeModelBindings(configuration).values());
        if (!capacity.allowed()) {
            throw exception(TASK_MODEL_CAPACITY_EXCEEDED, capacity.message());
        }
        return transactionTemplate.execute(status -> {
            // Pin the exact revision whose execution configuration passed validation.
            // A heartbeat arriving during preflight must not substitute unvalidated models.
            TaskDO task = requireLockedTask(id);
            if (!Objects.equals(task.getConfigVersion(), validated.getConfigVersion())
                    || !Objects.equals(task.getNodeId(), validated.getNodeId())
                    || gatewayRevision(task) != validatedGatewayRevision
                    || !Set.of("DRAFT", "STOPPED", "FAILED", "OFFLINE").contains(task.getActualStatus())) {
                throw exception(TASK_STATUS_INVALID);
            }
            String commandId = UUID.randomUUID().toString();
            String runId = UUID.randomUUID().toString();
            TaskRunDO run = new TaskRunDO();
            run.setTaskId(task.getId());
            run.setRunId(runId);
            run.setConfigVersion(task.getConfigVersion());
            run.setCommandId(commandId);
            run.setStatus("STARTING");
            taskRunMapper.insert(run);
            nodeCommandService.createCommand(commandId, task.getNodeId(), "START_TASK", task.getId(),
                    task.getConfigVersion(), "task-start:" + task.getId() + ":" + runId + ":gateway:" + gatewayRevision(task));
            task.setDesiredStatus("RUNNING");
            task.setActualStatus("STARTING");
            task.setActiveRunId(runId);
            task.setLastCommandId(commandId);
            clearError(task);
            if (taskMapper.claimStart(task) != 1) throw exception(TASK_STATUS_INVALID);
            return commandId;
        });
    }

    @Override
    public String stopTask(Long id) {
        return transactionTemplate.execute(status -> {
            TaskDO task = requireLockedTask(id);
            if ("STOPPED".equals(task.getActualStatus()) && "RUNNING".equals(task.getDesiredStatus())) {
                // A gateway may stop locally before the platform receives a stop command.
                // Reconcile the desired state without dispatching a redundant command.
                task.setDesiredStatus("STOPPED");
                clearError(task);
                taskMapper.updateRuntimeState(task);
                return null;
            }
            if (!Set.of("STARTING", "RUNNING", "STOPPING", "FAILED", "OFFLINE").contains(task.getActualStatus())
                    || task.getActiveRunId() == null) throw exception(TASK_STATUS_INVALID);
            if ("STOPPING".equals(task.getActualStatus()) && task.getLastCommandId() != null) {
                try {
                    NodeCommandDTO pending = nodeCommandService.getCommandForNode(
                            task.getLastCommandId(), task.getNodeId());
                    if ("STOP_TASK".equals(pending.getCommandType())
                            && Set.of("QUEUED", "SENT", "RUNNING").contains(pending.getStatus())) {
                        return pending.getCommandId();
                    }
                } catch (ServiceException error) {
                    // Recover rows left by the former retry bug: lastCommandId was a
                    // generated UUID although createCommand returned an existing ID.
                    if (!Objects.equals(error.getCode(), com.linsight.module.aivideo.enums.node
                            .ErrorCodeConstants.NODE_COMMAND_NOT_FOUND.getCode())) throw error;
                }
            }
            // Retries after a terminal failure need a new dispatchable command.
            // Concurrent callers with the same preceding command still deduplicate.
            String commandId = nodeCommandService.createCommand(UUID.randomUUID().toString(),
                    task.getNodeId(), "STOP_TASK", task.getId(), task.getConfigVersion(),
                    "task-stop:" + task.getId() + ":" + task.getActiveRunId() + ":"
                            + task.getLastCommandId() + ":gateway:" + gatewayRevision(task));
            task.setDesiredStatus("STOPPED");
            task.setActualStatus("STOPPING");
            task.setLastCommandId(commandId);
            clearError(task);
            taskMapper.updateRuntimeState(task);
            return commandId;
        });
    }

    @Override
    public TaskCommandDetailRespVO getCommandDetail(String commandId, Long nodeId) {
        NodeCommandDTO command = nodeCommandService.getCommandForNode(commandId, nodeId);
        if (!Set.of("START_TASK", "STOP_TASK", "APPLY_TASK_SETTINGS").contains(command.getCommandType())) {
            throw exception(TASK_NOT_FOUND);
        }
        TaskDO task = requireTask(command.getAggregateId());
        if (!Objects.equals(task.getNodeId(), nodeId)) throw exception(TASK_NOT_FOUND);
        boolean starting = "START_TASK".equals(command.getCommandType());
        TaskSaveReqVO configuration = starting ? executionConfiguration(task) : centralConfiguration(task);
        PipelineVersionDO pipeline = algorithmService.getPublishedPipeline(
                task.getAlgorithmId(), task.getPipelineVersionId());
        TaskCommandDetailRespVO detail = new TaskCommandDetailRespVO();
        String idempotency = command.getIdempotencyKey();
        if (idempotency != null && idempotency.contains(":gateway:")) {
            detail.setExpectedGatewayRevision(Long.parseLong(idempotency.substring(idempotency.lastIndexOf(":gateway:") + 9)));
        }
        detail.setCommandId(commandId);
        detail.setCommandType(command.getCommandType());
        detail.setConfigVersion(task.getConfigVersion());
        detail.setTaskId(task.getId());
        detail.setRunId(task.getActiveRunId());
        detail.setCameraId(task.getCameraId());
        if ("START_TASK".equals(command.getCommandType())) {
            detail.setStreamUrl(cameraService.getRuntimeStreamUrl(task.getCameraId(),
                    streamType(configuration.getParameters())));
            detail.setStreamUrls(cameraService.getRuntimeStreamUrls(task.getCameraId()));
        }
        detail.setAlgorithmId(task.getAlgorithmId());
        detail.setPipelineVersionId(task.getPipelineVersionId());
        detail.setPipeline(JsonUtils.parseMap(pipeline.getDag()));
        Map<String, String> displayNames = new LinkedHashMap<>();
        displayNames.put("task", task.getName());
        displayNames.put("camera", cameraService.getCameraNames(List.of(task.getCameraId()))
                .getOrDefault(task.getCameraId(), "摄像头 #" + task.getCameraId()));
        algorithmService.getSummaries(List.of(task.getAlgorithmId())).stream().findFirst()
                .ifPresent(value -> displayNames.put("algorithm", value.name()));
        detail.setDisplayNames(displayNames);
        if (detail.getPipeline().containsKey("algorithmPackage") && "START_TASK".equals(command.getCommandType())) {
            detail.setAlgorithmPackageUrl(algorithmPackageService.downloadUrl(pipeline.getId()));
            detail.setAlgorithmResources(algorithmPackageService.resources(detail.getPipeline(), configuration.getParameters(),
                    configuration.getModelBindings(), true));
        }
        detail.setModelVersionId(configuration.getModelVersionId());
        detail.setModelBindings(configuration.getModelBindings());
        if (configuration.getRuleId() != null) {
            RuleVersionConfigDTO rule = ruleService.getPublishedRuleConfig(
                    configuration.getRuleId(), configuration.getRuleVersionId());
            detail.setRuleId(rule.getRuleId());
            detail.setRuleVersionId(rule.getVersionId());
            detail.setRule(rule.getAst());
        }
        Map<String, Object> gatewayConfig = starting ? reusableGatewayConfiguration(task) : Map.of();
        if (gatewayConfig.containsKey("rule")) {
            detail.setRule(JsonUtils.parseMap(JsonUtils.toJsonString(gatewayConfig.get("rule"))));
        }
        detail.setParameters(configuration.getParameters());
        detail.setGlobalSettingsVersion(task.getGlobalSettingsVersion());
        detail.setGlobalSettings(JsonUtils.parseMap(task.getGlobalSettingsSnapshot()));
        return detail;
    }

    @Override
    public void applyCommandReport(NodeCommandDTO report) {
        if (!Set.of("START_TASK", "STOP_TASK", "APPLY_TASK_SETTINGS").contains(report.getCommandType())) return;
        transactionTemplate.executeWithoutResult(status -> {
            TaskDO task = taskMapper.selectByIdForUpdate(report.getAggregateId());
            // A command already in flight may finish after a local deletion.
            // Its receipt remains valid, but must not resurrect the removed task.
            if (task == null) return;
            boolean settings = "APPLY_TASK_SETTINGS".equals(report.getCommandType());
            if (!Objects.equals(task.getConfigVersion(), report.getConfigVersion())) return;
            if (settings ? !Objects.equals(report.getIdempotencyKey(),
                    "global-settings:" + task.getGlobalSettingsVersion() + ":task:" + task.getId())
                    : !Objects.equals(task.getLastCommandId(), report.getCommandId())) return;
            Map<String, Object> result = report.getResult();
            if (result != null && !result.isEmpty()) {
                if (!matchesRuntimeResult(task, result)) return;
                Map<String, Object> metrics = runtimeResultMetrics(result);
                boolean versioned = metrics.get("gatewayRevision") instanceof Number;
                if (versioned && gatewayRevision(metrics) < gatewayRevision(task)) return;
                if ("SUCCEEDED".equals(report.getStatus()) && !metrics.isEmpty()
                        && (versioned || gatewayRevision(task) == 0)) {
                    // Stop acknowledgements already carry revision N+1. Waiting for the
                    // next heartbeat lets an immediate restart reuse stale revision N.
                    task.setMetricsSnapshot(JsonUtils.toJsonString(metrics));
                }
            }
            if ("START_TASK".equals(report.getCommandType())) applyStartReport(task, report);
            else if ("STOP_TASK".equals(report.getCommandType())) applyStopReport(task, report);
            else applySettingsReport(task, report);
        });
    }

    @Override
    public void reportRuntime(Long nodeId, TaskRuntimeReportReqVO reqVO) {
        transactionTemplate.executeWithoutResult(status -> applyRuntimeReport(nodeId, reqVO));
    }

    @Override
    public void reportRemoval(Long nodeId, TaskRemovalReportReqVO reqVO) {
        transactionTemplate.executeWithoutResult(status -> {
            TaskDO task = taskMapper.selectByIdForUpdate(reqVO.getTaskId());
            if (task == null) return; // ACK replay, including a concurrent platform delete.
            if (!Objects.equals(task.getNodeId(), nodeId)
                    || !Objects.equals(task.getConfigVersion(), reqVO.getConfigVersion())
                    || reqVO.getGatewayRevision() <= gatewayRevision(task)) {
                throw exception(TASK_REPORT_STALE);
            }
            TaskRunDO run = taskRunMapper.selectByRunId(reqVO.getRunId());
            if (run == null || !Objects.equals(run.getTaskId(), task.getId())
                    || !Objects.equals(run.getConfigVersion(), reqVO.getConfigVersion())) {
                throw exception(TASK_REPORT_STALE);
            }
            Map<String, Object> metrics = new LinkedHashMap<>();
            if (task.getMetricsSnapshot() != null) metrics.putAll(JsonUtils.parseMap(task.getMetricsSnapshot()));
            metrics.put("schemaVersion", "1.0");
            metrics.put("gatewayRevision", reqVO.getGatewayRevision());
            metrics.put("gatewayRemoved", true);
            metrics.put("gatewayRemovalRequestId", reqVO.getRequestId());
            metrics.put("gatewayRemovedAt", reqVO.getRemovedAt());
            task.setMetricsSnapshot(JsonUtils.toJsonString(metrics));
            task.setActualStatus("STOPPED");
            task.setDesiredStatus("STOPPED");
            task.setLastHeartbeatTime(LocalDateTime.now());
            taskMapper.updateRuntimeState(task);
            run.setStatus("STOPPED");
            if (run.getFinishTime() == null) run.setFinishTime(LocalDateTime.now());
            run.setUpdater("edge-agent");
            run.setUpdateTime(LocalDateTime.now());
            taskRunMapper.updateById(run);
            // Logical deletion retains run and event history. No algorithm/model asset is deleted.
            // Node authentication has no admin user ID for MyBatis audit autofill.
            task.setUpdater("edge-agent");
            task.setUpdateTime(LocalDateTime.now());
            taskMapper.deleteById(task);
            log.info("Gateway task removed nodeId={} taskId={} revision={} requestId={}",
                    nodeId, task.getId(), reqVO.getGatewayRevision(), reqVO.getRequestId());
        });
    }

    private void applyRuntimeReport(Long nodeId, TaskRuntimeReportReqVO reqVO) {
        TaskRunDO run = taskRunMapper.selectByRunId(reqVO.getRunId());
        if (run == null) throw exception(TASK_RUN_NOT_FOUND);
        TaskDO task = requireLockedTask(run.getTaskId());
        if (!Objects.equals(task.getNodeId(), nodeId)
                || !Objects.equals(task.getConfigVersion(), reqVO.getConfigVersion())) {
            throw exception(TASK_REPORT_STALE);
        }
        if (!"1.0".equals(reqVO.getMetrics().get("schemaVersion"))) throw exception(TASK_CONFIG_INVALID);
        long observedRevision = gatewayRevision(reqVO.getMetrics());
        if (!Objects.equals(task.getActiveRunId(), reqVO.getRunId())) {
            // A rejected command never became the gateway's run. Its real run may
            // itself have failed; retain that failure and revision so retries can proceed.
            // Accept only a known run authenticated by this node and a newer revision.
            if (!"FAILED".equals(task.getActualStatus())
                    || !Set.of("RUNNING", "STOPPED").contains(task.getDesiredStatus())
                    || !isGatewayConflict(task.getErrorCode(), task.getErrorMessage())
                    || !Boolean.TRUE.equals(reqVO.getMetrics().get("gatewayPlatformManaged"))
                    || observedRevision <= gatewayRevision(task)
                    || !Set.of("RUNNING", "STOPPED", "FAILED").contains(reqVO.getStatus())) {
                throw exception(TASK_REPORT_STALE);
            }
            task.setActiveRunId(reqVO.getRunId());
        }
        if (observedRevision < gatewayRevision(task)) throw exception(TASK_REPORT_STALE);
        String metrics = JsonUtils.toJsonString(reqVO.getMetrics());
        // Heartbeats describe computation, not the completion of a pending stop command.
        boolean stopping = "STOPPED".equals(task.getDesiredStatus()) && "RUNNING".equals(reqVO.getStatus());
        boolean pendingStop = stopping && "STOPPING".equals(task.getActualStatus());
        boolean failedStop = stopping && task.getErrorCode() != null;
        task.setActualStatus(pendingStop ? "STOPPING" : reqVO.getStatus());
        task.setLastHeartbeatTime(LocalDateTime.now());
        task.setMetricsSnapshot(metrics);
        task.setDiagnosticId(reqVO.getDiagnosticId());
        if (!failedStop) {
            task.setErrorCode(reqVO.getErrorCode());
            task.setErrorMessage(reqVO.getErrorMessage());
        }
        taskMapper.updateRuntimeState(task);
        run.setStatus(reqVO.getStatus());
        run.setMetricsSnapshot(metrics);
        run.setDiagnosticId(reqVO.getDiagnosticId());
        run.setErrorCode(reqVO.getErrorCode());
        run.setErrorMessage(reqVO.getErrorMessage());
        if (Set.of("FAILED", "STOPPED").contains(reqVO.getStatus())) run.setFinishTime(LocalDateTime.now());
        taskRunMapper.updateById(run);
    }

    @Override
    public void validateRuntimeOverlay(Long nodeId, Long taskId, String runId, Long cameraId) {
        TaskDO task = requireTask(taskId);
        if (!Objects.equals(task.getNodeId(), nodeId)
                || !Objects.equals(task.getCameraId(), cameraId)
                || !Objects.equals(task.getActiveRunId(), runId)
                || !Objects.equals(task.getActualStatus(), "RUNNING")) {
            throw exception(TASK_REPORT_STALE);
        }
    }

    private void applyStartReport(TaskDO task, NodeCommandDTO report) {
        TaskRunDO run = taskRunMapper.selectByCommandId(report.getCommandId());
        if (run == null) throw exception(TASK_RUN_NOT_FOUND);
        if (!Objects.equals(run.getRunId(), task.getActiveRunId())) return;
        if ("SUCCEEDED".equals(report.getStatus())) {
            task.setActualStatus("RUNNING");
            task.setLastHeartbeatTime(LocalDateTime.now());
            run.setStatus("RUNNING");
            run.setStartTime(LocalDateTime.now());
        } else if (Set.of("FAILED", "EXPIRED").contains(report.getStatus())) {
            task.setActualStatus("FAILED");
            run.setStatus("FAILED");
            run.setFinishTime(LocalDateTime.now());
        }
        applyError(task, run, report);
        taskMapper.updateRuntimeState(task);
        taskRunMapper.updateById(run);
    }

    private void applyStopReport(TaskDO task, NodeCommandDTO report) {
        TaskRunDO run = taskRunMapper.selectByRunId(task.getActiveRunId());
        if (run == null) throw exception(TASK_RUN_NOT_FOUND);
        if ("SUCCEEDED".equals(report.getStatus())) {
            task.setActualStatus("STOPPED");
            // Keep the last run binding so an autonomous local restart can report its state.
            task.setLastHeartbeatTime(LocalDateTime.now());
            run.setStatus("STOPPED");
            run.setFinishTime(LocalDateTime.now());
        } else if (Set.of("FAILED", "EXPIRED").contains(report.getStatus())) {
            task.setActualStatus("FAILED");
        }
        applyError(task, run, report);
        taskMapper.updateRuntimeState(task);
        taskRunMapper.updateById(run);
    }

    private void applySettingsReport(TaskDO task, NodeCommandDTO report) {
        if ("SUCCEEDED".equals(report.getStatus())) {
            task.setAppliedGlobalSettingsVersion(task.getGlobalSettingsVersion());
            task.setErrorCode(null);
            task.setErrorMessage(null);
        } else if (Set.of("FAILED", "EXPIRED").contains(report.getStatus())) {
            task.setDiagnosticId(report.getDiagnosticId());
            task.setErrorCode(report.getErrorCode());
            task.setErrorMessage(report.getErrorMessage());
        }
        taskMapper.updateRuntimeState(task);
    }

    private PipelineVersionDO validateConfig(TaskSaveReqVO reqVO, boolean starting) {
        CameraDO camera = cameraService.getCamera(reqVO.getCameraId());
        if (!Objects.equals(camera.getStatus(), 0)) throw exception(TASK_CONFIG_INVALID);
        AlgorithmDO algorithm = algorithmService.getAlgorithm(reqVO.getAlgorithmId());
        if (!Objects.equals(algorithm.getStatus(), 0)) throw exception(TASK_CONFIG_INVALID);
        PipelineVersionDO pipeline = algorithmService.getPublishedPipeline(
                reqVO.getAlgorithmId(), reqVO.getPipelineVersionId());
        Object validationOnly = reqVO.getParameters().get("validationOnly");
        if (validationOnly != null && !(validationOnly instanceof Boolean)) throw exception(TASK_CONFIG_INVALID);
        streamType(reqVO.getParameters());
        algorithmService.validatePipelineRunnable(pipeline, Boolean.TRUE.equals(validationOnly));
        Map<String, Long> bindings = normalizeModelBindings(reqVO);
        Map<String, Object> dag = JsonUtils.parseMap(pipeline.getDag());
        if (dag.containsKey("algorithmPackage")) {
            algorithmPackageService.validateTask(dag, reqVO.getParameters(), bindings);
            if (starting && !nodeService.supportsAlgorithmPackages(reqVO.getNodeId())) {
                throw com.linsight.module.aivideo.service.algorithm.AlgorithmPackageValidator.invalid("当前网关需先在线升级，以支持算法包 SDK 1.0");
            }
        }
        Map<String, Set<Long>> nodeModelIds = pipelineModelIds(dag);
        Set<String> pipelineNodeIds = pipelineNodeIds(dag);
        for (Map.Entry<String, Long> binding : bindings.entrySet()) {
            if (!"primary".equals(binding.getKey()) && !pipelineNodeIds.contains(binding.getKey())) {
                throw exception(TASK_CONFIG_INVALID);
            }
            ModelVersionDO version = modelService.getVersion(binding.getValue());
            if (dag.containsKey("algorithmPackage")) algorithmPackageService.validateBinding(dag, binding.getKey(), version.getArtifactFormat(), version.getRuntimeManifest());
            validateBindingLabels(dag, binding.getKey(), version.getRuntimeManifest());
            Set<Long> expectedModelIds = nodeModelIds.get(binding.getKey());
            if ((expectedModelIds == null || expectedModelIds.isEmpty())
                    && algorithm.getDefaultModelId() != null) {
                expectedModelIds = Set.of(algorithm.getDefaultModelId());
            }
            if (expectedModelIds != null && !expectedModelIds.isEmpty()
                    && !expectedModelIds.contains(version.getModelId())) {
                throw exception(TASK_CONFIG_INVALID);
            }
            if (!"PUBLISHED".equals(version.getPublishStatus()) || !"READY".equals(version.getExecutionStatus())) {
                throw exception(TASK_CONFIG_INVALID);
            }
            if (starting) modelExecutionService.validateDeploymentReady(binding.getValue(), reqVO.getNodeId());
        }
        if (!"1.0".equals(reqVO.getParameters().get("schemaVersion"))) {
            throw exception(TASK_CONFIG_INVALID);
        }
        if (starting) nodeService.validateNodeAvailable(reqVO.getNodeId());
        else nodeService.validateNodeExists(reqVO.getNodeId());
        if ((reqVO.getRuleId() == null) != (reqVO.getRuleVersionId() == null)) {
            throw exception(TASK_CONFIG_INVALID);
        }
        if (reqVO.getRuleId() != null) {
            RuleVersionConfigDTO rule = ruleService.getPublishedRuleConfig(
                    reqVO.getRuleId(), reqVO.getRuleVersionId());
            String eventType = algorithmPackageService.eventType(pipeline.getId(), algorithm.getEventType());
            if (eventType != null && !Objects.equals(eventType, rule.getEventType())) {
                throw exception(TASK_CONFIG_INVALID);
            }
        }
        return pipeline;
    }

    private TaskSaveReqVO executionConfiguration(TaskDO task) {
        TaskSaveReqVO reqVO = centralConfiguration(task);
        Map<String, Object> gateway = reusableGatewayConfiguration(task);
        if (!gateway.isEmpty()) {
            if (!(gateway.get("modelBindings") instanceof Map<?, ?> bindings) || bindings.isEmpty()
                    || bindings.values().stream().anyMatch(value -> !(value instanceof Number))
                    || !(gateway.get("parameters") instanceof Map<?, ?>)) {
                throw exception(TASK_CONFIG_INVALID);
            }
            reqVO.setModelVersionId(optionalConfigurationId(gateway.get("modelVersionId")));
            reqVO.setModelBindings(TaskConvert.parseModelBindings(
                    JsonUtils.toJsonString(bindings), reqVO.getModelVersionId()));
            reqVO.setParameters(JsonUtils.parseMap(JsonUtils.toJsonString(gateway.get("parameters"))));
            reqVO.setRuleId(optionalConfigurationId(gateway.get("ruleId")));
            reqVO.setRuleVersionId(optionalConfigurationId(gateway.get("ruleVersionId")));
        }
        return reqVO;
    }

    private static String streamType(Map<String, Object> parameters) {
        Object selected = parameters.get("streamType");
        if (selected == null) return "SUB"; // Existing tasks keep their current source.
        if ("MAIN".equals(selected) || "SUB".equals(selected)) return (String) selected;
        throw exception(TASK_CONFIG_INVALID);
    }

    private static TaskSaveReqVO centralConfiguration(TaskDO task) {
        TaskSaveReqVO reqVO = new TaskSaveReqVO();
        reqVO.setCameraId(task.getCameraId());
        reqVO.setAlgorithmId(task.getAlgorithmId());
        reqVO.setPipelineVersionId(task.getPipelineVersionId());
        reqVO.setModelVersionId(task.getModelVersionId());
        reqVO.setModelBindings(TaskConvert.parseModelBindings(task.getModelBindings(), task.getModelVersionId()));
        reqVO.setNodeId(task.getNodeId());
        reqVO.setRuleId(task.getRuleId());
        reqVO.setRuleVersionId(task.getRuleVersionId());
        reqVO.setParameters(JsonUtils.parseMap(task.getParameters()));
        return reqVO;
    }

    static Map<String, Object> reusableGatewayConfiguration(TaskDO task) {
        Map<String, Object> metrics = JsonUtils.parseMap(task.getMetricsSnapshot());
        if (metrics == null || gatewayRevision(metrics) <= 0
                || !Boolean.TRUE.equals(metrics.get("gatewayPlatformManaged"))
                || !(metrics.get("gatewayConfiguration") instanceof Map<?, ?> raw)) return Map.of();
        Long version = optionalConfigurationId(raw.get("configVersion"));
        if (version == null) throw exception(TASK_CONFIG_INVALID);
        // An explicit central edit creates a new configVersion. Only that edit may
        // replace gateway settings; restarting the same version reuses local changes.
        if (version < task.getConfigVersion()) return Map.of();
        if (version != task.getConfigVersion().longValue()
                || !Objects.equals(optionalConfigurationId(raw.get("taskId")), task.getId())
                || !Objects.equals(optionalConfigurationId(raw.get("cameraId")), task.getCameraId())
                || !Objects.equals(optionalConfigurationId(raw.get("algorithmId")), task.getAlgorithmId())
                || !Objects.equals(optionalConfigurationId(raw.get("pipelineVersionId")), task.getPipelineVersionId())) {
            throw exception(TASK_CONFIG_INVALID);
        }
        return JsonUtils.parseMap(JsonUtils.toJsonString(raw));
    }

    private static Long optionalConfigurationId(Object value) {
        if (value == null) return null;
        if (!(value instanceof Number number)) throw exception(TASK_CONFIG_INVALID);
        return number.longValue();
    }

    private static long gatewayRevision(TaskDO task) {
        Map<String, Object> metrics = JsonUtils.parseMap(task.getMetricsSnapshot());
        return gatewayRevision(metrics);
    }

    private static long gatewayRevision(Map<String, Object> metrics) {
        return metrics != null && metrics.get("gatewayRevision") instanceof Number revision
                ? revision.longValue() : 0L;
    }

    private static boolean matchesRuntimeResult(TaskDO task, Map<String, Object> result) {
        return result.get("taskId") instanceof Number taskId && taskId.longValue() == task.getId()
                && result.get("configVersion") instanceof Number version && version.intValue() == task.getConfigVersion()
                && Objects.equals(result.get("runId"), task.getActiveRunId());
    }

    private static Map<String, Object> runtimeResultMetrics(Map<String, Object> result) {
        if (!(result.get("metrics") instanceof Map<?, ?> metrics)
                || !"1.0".equals(metrics.get("schemaVersion"))) return Map.of();
        Map<String, Object> value = new LinkedHashMap<>();
        metrics.forEach((key, item) -> value.put(String.valueOf(key), item));
        return value;
    }

    private TaskDO requireLockedTask(Long id) {
        TaskDO task = id == null ? null : taskMapper.selectByIdForUpdate(id);
        if (task == null) throw exception(TASK_NOT_FOUND);
        return task;
    }

    private TaskDO requireTask(Long id) {
        TaskDO task = id == null ? null : taskMapper.selectById(id);
        if (task == null) throw exception(TASK_NOT_FOUND);
        return task;
    }

    private static TaskDO toTask(TaskSaveReqVO reqVO, Long pipelineVersionId) {
        TaskDO task = new TaskDO();
        task.setId(reqVO.getId());
        task.setName(reqVO.getName());
        task.setCode(reqVO.getCode());
        task.setCameraId(reqVO.getCameraId());
        task.setAlgorithmId(reqVO.getAlgorithmId());
        task.setPipelineVersionId(pipelineVersionId);
        Map<String, Long> bindings = normalizeModelBindings(reqVO);
        Long primaryVersionId = reqVO.getModelVersionId() != null
                ? reqVO.getModelVersionId() : bindings.values().iterator().next();
        task.setModelVersionId(primaryVersionId);
        task.setModelBindings(JsonUtils.toJsonString(bindings));
        task.setNodeId(reqVO.getNodeId());
        task.setRuleId(reqVO.getRuleId());
        task.setRuleVersionId(reqVO.getRuleVersionId());
        task.setParameters(JsonUtils.toJsonString(reqVO.getParameters()));
        return task;
    }

    static void validateBindingLabels(Map<String, Object> dag, String nodeId, String manifest) {
        if (!(dag.get("nodes") instanceof List<?> nodes)) return;
        String capability = nodes.stream().filter(Map.class::isInstance).map(value -> (Map<?, ?>) value)
                .filter(node -> Objects.equals(nodeId, node.get("id")))
                .map(node -> String.valueOf(node.get("capabilityKey"))).findFirst().orElse("");
        Set<String> required = switch (capability) {
            case "detector.person" -> Set.of("person");
            case "ppe.helmet" -> Set.of("helmet", "no_helmet");
            case "ppe.reflective-vest" -> Set.of("vest", "no_vest");
            default -> Set.of();
        };
        if (required.isEmpty()) return;
        Set<String> labels = new java.util.HashSet<>();
        try {
            var root = JsonUtils.parseTree(manifest == null ? "{}" : manifest);
            root.path("decoder").path("labels").forEach(label -> labels.add(label.asText()));
        } catch (RuntimeException ignored) { /* Fail closed on missing or malformed metadata. */ }
        if (!labels.containsAll(required)) throw exception(TASK_MODEL_CAPABILITY_MISMATCH,
                nodeId, String.join(", ", new java.util.TreeSet<>(required)));
    }

    private static Map<String, Long> normalizeModelBindings(TaskSaveReqVO reqVO) {
        Map<String, Long> result = new LinkedHashMap<>();
        if (reqVO.getModelBindings() != null) result.putAll(reqVO.getModelBindings());
        if (result.isEmpty() && reqVO.getModelVersionId() != null) result.put("primary", reqVO.getModelVersionId());
        if (result.isEmpty()) throw exception(TASK_CONFIG_INVALID);
        if (reqVO.getModelVersionId() != null && !result.containsValue(reqVO.getModelVersionId())) {
            result.put("primary", reqVO.getModelVersionId());
        }
        return result;
    }

    private static Map<String, Set<Long>> pipelineModelIds(Map<String, Object> dag) {
        Map<String, Set<Long>> result = new LinkedHashMap<>();
        if (dag == null || !(dag.get("nodes") instanceof List<?> nodes)) return result;
        for (Object value : nodes) {
            if (!(value instanceof Map<?, ?> node) || !(node.get("id") instanceof String id)) continue;
            Set<Long> ids = new LinkedHashSet<>();
            if (node.get("modelId") instanceof Number modelId) ids.add(modelId.longValue());
            if (node.get("modelIds") instanceof List<?> modelIds) {
                modelIds.stream().filter(Number.class::isInstance).map(Number.class::cast)
                        .map(Number::longValue).forEach(ids::add);
            }
            if (!ids.isEmpty()) result.put(id, ids);
        }
        return result;
    }

    private static Set<String> pipelineNodeIds(Map<String, Object> dag) {
        Set<String> result = new java.util.LinkedHashSet<>();
        if (dag == null || !(dag.get("nodes") instanceof List<?> nodes)) return result;
        for (Object value : nodes) {
            if (value instanceof Map<?, ?> node && node.get("id") instanceof String id) {
                result.add(id);
            }
        }
        return result;
    }

    private void validateConfirmationLatency(Map<String, Object> parameters, Long ruleId,
                                             Long ruleVersionId) {
        if (ruleId == null || ruleVersionId == null) return;
        validateConfirmationLatency(parameters,
                ruleService.getPublishedRuleConfig(ruleId, ruleVersionId));
    }

    private static void validateConfirmationLatency(Map<String, Object> parameters,
                                                    RuleVersionConfigDTO rule) {
        // Long-duration dwell/absence rules express the business condition itself.
        // This guard targets the PHONE_CALL behavior flow requested to be visible in 2s.
        if (!"PHONE_CALL".equals(rule.getEventType())) return;
        Object rawFps = parameters == null ? null : parameters.get("sampleFps");
        if (!(rawFps instanceof Number number) || !Double.isFinite(number.doubleValue())
                || number.doubleValue() <= 0) {
            throw exception(TASK_CONFIG_INVALID);
        }
        RuleAstValidator.ConfirmationLatency estimate = RuleAstValidator
                .estimateConfirmationLatency(rule.getAst(), number.doubleValue());
        if (estimate.conflictsWithEventVisibilityTarget()) {
            throw exception(TASK_CONFIRMATION_LATENCY_CONFLICT,
                    String.format(Locale.ROOT, "%.2f", estimate.minimumSeconds()));
        }
    }

    private static boolean confirmationConfigurationChanged(TaskDO existing,
                                                             TaskSaveReqVO requested) {
        if (!Objects.equals(existing.getRuleId(), requested.getRuleId())
                || !Objects.equals(existing.getRuleVersionId(), requested.getRuleVersionId())) {
            return true;
        }
        Map<String, Object> previous = JsonUtils.parseMap(existing.getParameters());
        Object previousFps = previous.get("sampleFps");
        Object requestedFps = requested.getParameters() == null
                ? null : requested.getParameters().get("sampleFps");
        return !(previousFps instanceof Number left) || !(requestedFps instanceof Number right)
                || Double.compare(left.doubleValue(), right.doubleValue()) != 0;
    }

    private static void applyError(TaskDO task, TaskRunDO run, NodeCommandDTO report) {
        task.setDiagnosticId(report.getDiagnosticId());
        boolean conflict = isGatewayConflict(report.getErrorCode(), report.getErrorMessage());
        task.setErrorCode(conflict ? "TASK_GATEWAY_CONFLICT" : report.getErrorCode());
        task.setErrorMessage(conflict ? "网关配置已更新，正在同步最新状态；同步后可重新操作" : report.getErrorMessage());
        run.setDiagnosticId(report.getDiagnosticId());
        run.setErrorCode(report.getErrorCode());
        run.setErrorMessage(report.getErrorMessage());
    }

    private static boolean isGatewayConflict(String code, String message) {
        return "TASK_GATEWAY_CONFLICT".equals(code) || ("MODEL_COMMAND_FAILED".equals(code)
                && ("GatewayConflict".equals(message)
                || (message != null && (message.contains("gateway configuration changed")
                || message.contains("run changed before stop")))));
    }

    private static void clearError(TaskDO task) {
        task.setDiagnosticId(null);
        task.setErrorCode(null);
        task.setErrorMessage(null);
    }
}
