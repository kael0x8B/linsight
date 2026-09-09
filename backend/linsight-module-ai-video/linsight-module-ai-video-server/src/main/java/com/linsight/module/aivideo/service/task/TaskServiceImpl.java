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
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

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
                    metrics.path("executionBackend").asText(null), task.getErrorCode(), task.getErrorMessage());
        }).toList();
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
        if (!Objects.equals(algorithm.eventType(), rule.getEventType())) throw exception(TASK_CONFIG_INVALID);
        if (Objects.equals(task.getRuleId(), reqVO.getRuleId())
                && Objects.equals(task.getRuleVersionId(), reqVO.getRuleVersionId())
                && (Objects.equals(task.getConfigVersion(), reqVO.getExpectedConfigVersion())
                    || task.getConfigVersion() == reqVO.getExpectedConfigVersion() + 1)) return;
        if (taskMapper.updateRuleVersion(task.getId(), reqVO.getExpectedConfigVersion(),
                reqVO.getRuleId(), reqVO.getRuleVersionId()) != 1) throw exception(TASK_CONFIG_INVALID);
    }

    @Override
    public void deleteTask(Long id) {
        TaskDO task = requireTask(id);
        if (!Set.of("DRAFT", "STOPPED").contains(task.getActualStatus())) throw exception(TASK_STATUS_INVALID);
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
    public String startTask(Long id) {
        TaskDO task = requireTask(id);
        if (!Set.of("DRAFT", "STOPPED", "FAILED", "OFFLINE").contains(task.getActualStatus())) {
            throw exception(TASK_STATUS_INVALID);
        }
        validateConfig(task);
        return transactionTemplate.execute(status -> {
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
        TaskDO task = requireTask(id);
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
        return transactionTemplate.execute(status -> {
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
            detail.setStreamUrl(cameraService.getRuntimeStreamUrl(task.getCameraId(), "SUB"));
        }
        detail.setAlgorithmId(task.getAlgorithmId());
        detail.setPipelineVersionId(task.getPipelineVersionId());
        detail.setPipeline(JsonUtils.parseMap(pipeline.getDag()));
        detail.setModelVersionId(task.getModelVersionId());
        detail.setModelBindings(TaskConvert.parseModelBindings(task.getModelBindings(), task.getModelVersionId()));
        if (task.getRuleId() != null) {
            RuleVersionConfigDTO rule = ruleService.getPublishedRuleConfig(
                    task.getRuleId(), task.getRuleVersionId());
            detail.setRuleId(rule.getRuleId());
            detail.setRuleVersionId(rule.getVersionId());
            detail.setRule(rule.getAst());
        }
        detail.setParameters(JsonUtils.parseMap(task.getParameters()));
        detail.setGlobalSettingsVersion(task.getGlobalSettingsVersion());
        detail.setGlobalSettings(JsonUtils.parseMap(task.getGlobalSettingsSnapshot()));
        return detail;
    }

    @Override
    public void applyCommandReport(NodeCommandDTO report) {
        if (!Set.of("START_TASK", "STOP_TASK", "APPLY_TASK_SETTINGS").contains(report.getCommandType())) return;
        transactionTemplate.executeWithoutResult(status -> {
            TaskDO task = requireTask(report.getAggregateId());
            if ("START_TASK".equals(report.getCommandType())) applyStartReport(task, report);
            else if ("STOP_TASK".equals(report.getCommandType())) applyStopReport(task, report);
            else applySettingsReport(task, report);
        });
    }

    @Override
    public void reportRuntime(Long nodeId, TaskRuntimeReportReqVO reqVO) {
        TaskRunDO run = taskRunMapper.selectByRunId(reqVO.getRunId());
        if (run == null) throw exception(TASK_RUN_NOT_FOUND);
        TaskDO task = requireTask(run.getTaskId());
        if (!Objects.equals(task.getNodeId(), nodeId) || !Objects.equals(task.getActiveRunId(), reqVO.getRunId())
                || !Objects.equals(task.getConfigVersion(), reqVO.getConfigVersion())) {
            throw exception(TASK_REPORT_STALE);
        }
        if (!"1.0".equals(reqVO.getMetrics().get("schemaVersion"))) throw exception(TASK_CONFIG_INVALID);
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
        algorithmService.validatePipelineRunnable(pipeline, Boolean.TRUE.equals(validationOnly));
        Map<String, Long> bindings = normalizeModelBindings(reqVO);
        Map<String, Object> dag = JsonUtils.parseMap(pipeline.getDag());
        Map<String, Long> nodeModelIds = pipelineModelIds(dag);
        Set<String> pipelineNodeIds = pipelineNodeIds(dag);
        for (Map.Entry<String, Long> binding : bindings.entrySet()) {
            if (!"primary".equals(binding.getKey()) && !pipelineNodeIds.contains(binding.getKey())) {
                throw exception(TASK_CONFIG_INVALID);
            }
            ModelVersionDO version = modelService.getVersion(binding.getValue());
            validateBindingLabels(dag, binding.getKey(), version.getRuntimeManifest());
            Long expectedModelId = nodeModelIds.get(binding.getKey());
            if (expectedModelId == null) {
                expectedModelId = algorithm.getDefaultModelId();
            }
            if (expectedModelId != null && !Objects.equals(expectedModelId, version.getModelId())) {
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
            if (algorithm.getEventType() != null && !Objects.equals(algorithm.getEventType(), rule.getEventType())) {
                throw exception(TASK_CONFIG_INVALID);
            }
        }
        return pipeline;
    }

    private void validateConfig(TaskDO task) {
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
        validateConfig(reqVO, true);
    }

    private static long gatewayRevision(TaskDO task) {
        Map<String, Object> metrics = JsonUtils.parseMap(task.getMetricsSnapshot());
        return metrics != null && metrics.get("gatewayRevision") instanceof Number revision
                ? revision.longValue() : 0L;
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

    private static Map<String, Long> pipelineModelIds(Map<String, Object> dag) {
        Map<String, Long> result = new LinkedHashMap<>();
        if (dag == null || !(dag.get("nodes") instanceof List<?> nodes)) return result;
        for (Object value : nodes) {
            if (!(value instanceof Map<?, ?> node) || !(node.get("id") instanceof String id)
                    || !(node.get("modelId") instanceof Number modelId)) continue;
            result.put(id, modelId.longValue());
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

    private static void applyError(TaskDO task, TaskRunDO run, NodeCommandDTO report) {
        task.setDiagnosticId(report.getDiagnosticId());
        task.setErrorCode(report.getErrorCode());
        task.setErrorMessage(report.getErrorMessage());
        run.setDiagnosticId(report.getDiagnosticId());
        run.setErrorCode(report.getErrorCode());
        run.setErrorMessage(report.getErrorMessage());
    }

    private static void clearError(TaskDO task) {
        task.setDiagnosticId(null);
        task.setErrorCode(null);
        task.setErrorMessage(null);
    }
}
