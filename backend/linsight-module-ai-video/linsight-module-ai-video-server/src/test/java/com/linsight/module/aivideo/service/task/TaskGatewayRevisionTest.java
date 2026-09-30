package com.linsight.module.aivideo.service.task;

import com.linsight.framework.common.exception.ServiceException;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.module.aivideo.controller.node.task.vo.TaskRuntimeReportReqVO;
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
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.HashMap;
import java.util.Map;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class TaskGatewayRevisionTest {
    private final TaskMapper tasks = mock(TaskMapper.class);
    private final TaskRunMapper runs = mock(TaskRunMapper.class);
    private final NodeCommandService commands = mock(NodeCommandService.class);
    private final NodeService nodes = mock(NodeService.class);
    private final ModelService models = mock(ModelService.class);
    private final ModelExecutionService deployments = mock(ModelExecutionService.class);
    private final AlgorithmService algorithms = mock(AlgorithmService.class);
    private final CameraService cameraService = mock(CameraService.class);
    private final TaskServiceImpl service = new TaskServiceImpl();
    private final TaskDO task = new TaskDO();
    private final Map<String, TaskRunDO> knownRuns = new HashMap<>();

    TaskGatewayRevisionTest() {
        ReflectionTestUtils.setField(service, "taskMapper", tasks);
        ReflectionTestUtils.setField(service, "taskRunMapper", runs);
        ReflectionTestUtils.setField(service, "nodeCommandService", commands);
        ReflectionTestUtils.setField(service, "nodeService", nodes);
        ReflectionTestUtils.setField(service, "cameraService", cameraService);
        ReflectionTestUtils.setField(service, "algorithmService", algorithms);
        ReflectionTestUtils.setField(service, "modelService", models);
        ReflectionTestUtils.setField(service, "modelExecutionService", deployments);
        ReflectionTestUtils.setField(service, "transactionTemplate",
                new TransactionTemplate(mock(PlatformTransactionManager.class)));
        task.setId(21L); task.setNodeId(5L); task.setCameraId(2L);
        task.setAlgorithmId(7L); task.setPipelineVersionId(8L); task.setModelVersionId(125L);
        task.setConfigVersion(2); task.setActiveRunId("old-run"); task.setLastCommandId("stop-old");
        task.setDesiredStatus("STOPPED"); task.setActualStatus("STOPPING");
        task.setParameters("{\"schemaVersion\":\"1.0\"}");
        task.setMetricsSnapshot(JsonUtils.toJsonString(metrics(3)));
        when(tasks.selectById(21L)).thenReturn(task);
        when(tasks.selectByIdForUpdate(21L)).thenReturn(task);
        when(tasks.claimStart(any())).thenReturn(1);
        when(commands.createCommand(anyString(), anyLong(), anyString(), anyLong(), anyInt(), anyString()))
                .thenAnswer(call -> call.getArgument(0));
        when(nodes.preflightTaskCapacity(anyLong(), anyLong(), anyCollection())).thenReturn(
                new com.linsight.module.aivideo.service.node.NodeTaskCapacityPreflightDTO(
                        true, null, "容量预检通过", Map.of("allowed", true)));
        when(runs.selectByRunId(anyString())).thenAnswer(call -> knownRuns.get(call.getArgument(0)));
        when(runs.selectByCommandId(anyString())).thenAnswer(call -> knownRuns.values().stream()
                .filter(run -> run.getCommandId().equals(call.getArgument(0))).findFirst().orElse(null));
        when(runs.insert(any(TaskRunDO.class))).thenAnswer(call -> {
            TaskRunDO run = call.getArgument(0); knownRuns.put(run.getRunId(), run); return 1;
        });
        remember("old-run", "start-old", "RUNNING");
        CameraDO camera = new CameraDO(); camera.setStatus(0);
        when(cameraService.getCamera(2L)).thenReturn(camera);
        AlgorithmDO algorithm = new AlgorithmDO(); algorithm.setStatus(0); algorithm.setDefaultModelId(9L);
        when(algorithms.getAlgorithm(7L)).thenReturn(algorithm);
        PipelineVersionDO pipeline = new PipelineVersionDO(); pipeline.setId(8L);
        pipeline.setDag("{\"schemaVersion\":\"1.0\",\"nodes\":[]}");
        when(algorithms.getPublishedPipeline(7L, 8L)).thenReturn(pipeline);
        ModelVersionDO model = new ModelVersionDO(); model.setModelId(9L);
        model.setPublishStatus("PUBLISHED"); model.setExecutionStatus("READY");
        when(models.getVersion(125L)).thenReturn(model);
    }

    private void remember(String id, String commandId, String status) {
        TaskRunDO run = new TaskRunDO(); run.setTaskId(21L); run.setRunId(id);
        run.setCommandId(commandId); run.setConfigVersion(2); run.setStatus(status);
        knownRuns.put(id, run);
    }

    private Map<String, Object> metrics(long revision) {
        return Map.of("schemaVersion", "1.0", "gatewayRevision", revision,
                "gatewayAppliedRevision", revision, "gatewayPlatformManaged", true);
    }

    private Map<String, Object> localConfiguration() {
        Map<String, Object> config = new HashMap<>();
        config.put("taskId", 21); config.put("cameraId", 2);
        config.put("algorithmId", 7); config.put("pipelineVersionId", 8);
        config.put("configVersion", 2); config.put("modelVersionId", 126);
        config.put("modelBindings", Map.of("primary", 126));
        config.put("parameters", Map.of("schemaVersion", "1.0", "sampleFps", 4, "validationOnly", true));
        config.put("rule", Map.of("schemaVersion", "1.0", "regions", java.util.List.of()));
        return config;
    }

    private void reportConfiguration(long revision, Map<String, Object> configuration) {
        Map<String, Object> snapshot = new HashMap<>(metrics(revision));
        snapshot.put("gatewayConfiguration", configuration);
        task.setMetricsSnapshot(JsonUtils.toJsonString(snapshot));
    }

    private void prepareLocalModelChange() {
        task.setActualStatus("STOPPED");
        models.getVersion(125L).setPublishStatus("SUPERSEDED");
        ModelVersionDO replacement = new ModelVersionDO(); replacement.setModelId(9L);
        replacement.setPublishStatus("PUBLISHED"); replacement.setExecutionStatus("READY");
        when(models.getVersion(126L)).thenReturn(replacement);
        clearInvocations(models);
        reportConfiguration(4, localConfiguration());
    }

    @Test
    void restartValidatesAndDispatchesGatewayModelsAndParametersInsteadOfSupersededCentralBinding() {
        prepareLocalModelChange();
        String commandId = service.startTask(21L);
        verify(models, never()).getVersion(125L);
        verify(deployments).validateDeploymentReady(126L, 5L);
        verify(nodes).preflightTaskCapacity(eq(5L), eq(21L), argThat(ids -> ids.equals(java.util.List.of(126L))
                || new java.util.HashSet<>(ids).equals(java.util.Set.of(126L))));
        verify(algorithms).validatePipelineRunnable(any(), eq(true));
        verify(commands).createCommand(anyString(), eq(5L), eq("START_TASK"), eq(21L), eq(2), endsWith(":gateway:4"));

        NodeCommandDTO command = ack("START_TASK", commandId, 4);
        command.setIdempotencyKey("task-start:21:run:gateway:4");
        when(commands.getCommandForNode(commandId, 5L)).thenReturn(command);
        var detail = service.getCommandDetail(commandId, 5L);
        assertThat(detail.getModelBindings()).containsExactlyEntriesOf(Map.of("primary", 126L));
        assertThat(detail.getModelVersionId()).isEqualTo(126L);
        assertThat(detail.getParameters()).containsEntry("sampleFps", 4);
        assertThat(detail.getRule()).containsEntry("regions", java.util.List.of());
        assertThat(detail.getExpectedGatewayRevision()).isEqualTo(4);
        // The gateway is the execution owner; a restart does not rewrite central intent.
        assertThat(task.getModelVersionId()).isEqualTo(125L);
        assertThat(task.getConfigVersion()).isEqualTo(2);
    }

    @Test
    void gatewaySelectedMainStreamIsDispatchedWhileLegacyTasksKeepSubStream() {
        prepareLocalModelChange();
        Map<String, Object> configuration = localConfiguration();
        configuration.put("parameters", Map.of("schemaVersion", "1.0", "streamType", "MAIN",
                "sampleFps", 2, "validationOnly", true));
        reportConfiguration(4, configuration);
        when(cameraService.getRuntimeStreamUrl(2L, "MAIN")).thenReturn("rtsp://camera/main");
        when(cameraService.getRuntimeStreamUrls(2L)).thenReturn(Map.of(
                "MAIN", "rtsp://camera/main", "SUB", "rtsp://camera/sub"));

        String commandId = service.startTask(21L);
        NodeCommandDTO command = ack("START_TASK", commandId, 4);
        command.setIdempotencyKey("task-start:21:run:gateway:4");
        when(commands.getCommandForNode(commandId, 5L)).thenReturn(command);
        assertThat(service.getCommandDetail(commandId, 5L).getStreamUrl()).isEqualTo("rtsp://camera/main");
        assertThat(service.getCommandDetail(commandId, 5L).getStreamUrls())
                .containsEntry("MAIN", "rtsp://camera/main").containsEntry("SUB", "rtsp://camera/sub");
        verify(cameraService, never()).getRuntimeStreamUrl(2L, "SUB");
    }

    @Test
    void activePreviewUsesGatewaySelectedStreamAndLegacyTasksUseSubStream() {
        task.setActualStatus("RUNNING");
        when(tasks.selectList(any(com.baomidou.mybatisplus.core.conditions.Wrapper.class)))
                .thenReturn(java.util.List.of(task));
        assertThat(service.getActiveStreamType(2L, 5L)).isEqualTo("SUB");
        Map<String, Object> configuration = localConfiguration();
        configuration.put("parameters", Map.of("schemaVersion", "1.0", "streamType", "MAIN"));
        reportConfiguration(4, configuration);
        assertThat(service.getActiveStreamType(2L, 5L)).isEqualTo("MAIN");
    }

    @Test
    void explicitCentralConfigurationEditSupersedesOlderGatewaySnapshot() {
        prepareLocalModelChange();
        models.getVersion(125L).setPublishStatus("PUBLISHED");
        clearInvocations(models);
        task.setConfigVersion(3);
        service.startTask(21L);
        verify(models).getVersion(125L);
        verify(models, never()).getVersion(126L);
        verify(deployments).validateDeploymentReady(125L, 5L);
    }

    @ParameterizedTest
    @ValueSource(strings = {"unpublished", "not-ready", "not-deployed", "invalid-parameters", "different-model"})
    void gatewayConfigurationStillPassesAllExistingModelAndParameterGates(String invalid) {
        prepareLocalModelChange();
        switch (invalid) {
            case "unpublished" -> models.getVersion(126L).setPublishStatus("DRAFT");
            case "not-ready" -> models.getVersion(126L).setExecutionStatus("FAILED");
            case "not-deployed" -> doThrow(new ServiceException(400, "deployment not ready"))
                    .when(deployments).validateDeploymentReady(126L, 5L);
            case "different-model" -> models.getVersion(126L).setModelId(99L);
            case "invalid-parameters" -> {
                Map<String, Object> config = localConfiguration();
                config.put("parameters", Map.of("schemaVersion", "1.0", "validationOnly", "true"));
                reportConfiguration(4, config);
            }
        }
        assertThatThrownBy(() -> service.startTask(21L)).isInstanceOf(ServiceException.class);
        verify(tasks, never()).claimStart(any());
        verify(runs, never()).insert(any(TaskRunDO.class));
    }

    @ParameterizedTest
    @ValueSource(strings = {"taskId", "cameraId", "algorithmId", "pipelineVersionId", "configVersion", "modelBindings", "parameters"})
    void unrelatedOrIncompleteGatewayConfigurationCannotBeUsedForStart(String invalid) {
        prepareLocalModelChange();
        Map<String, Object> config = localConfiguration();
        config.put(invalid, 999);
        reportConfiguration(4, config);
        assertThatThrownBy(() -> service.startTask(21L)).isInstanceOf(ServiceException.class);
        verify(tasks, never()).claimStart(any());
    }

    @Test
    void localChangeDuringPreflightCannotQueueStartAgainstUnvalidatedRevision() {
        prepareLocalModelChange();
        when(nodes.preflightTaskCapacity(eq(5L), eq(21L), anyCollection())).thenAnswer(call -> {
            Map<String, Object> changed = localConfiguration();
            changed.put("modelBindings", Map.of("primary", 999));
            reportConfiguration(5, changed);
            return new com.linsight.module.aivideo.service.node.NodeTaskCapacityPreflightDTO(
                    true, null, "容量预检通过", Map.of("allowed", true));
        });
        assertThatThrownBy(() -> service.startTask(21L)).isInstanceOf(ServiceException.class);
        verify(tasks, never()).claimStart(any());
        verify(runs, never()).insert(any(TaskRunDO.class));
    }

    private NodeCommandDTO ack(String type, String commandId, long revision) {
        NodeCommandDTO result = new NodeCommandDTO();
        result.setCommandId(commandId); result.setAggregateId(21L); result.setNodeId(5L);
        result.setConfigVersion(2); result.setCommandType(type); result.setStatus("SUCCEEDED");
        result.setResult(Map.of("taskId", 21, "runId", task.getActiveRunId(), "configVersion", 2,
                "status", "STOP_TASK".equals(type) ? "STOPPED" : "RUNNING", "metrics", metrics(revision)));
        return result;
    }

    private TaskRuntimeReportReqVO heartbeat(String runId, long revision) {
        TaskRuntimeReportReqVO result = new TaskRuntimeReportReqVO();
        result.setRunId(runId); result.setConfigVersion(2); result.setStatus("STOPPED");
        result.setMetrics(metrics(revision));
        return result;
    }

    private void rejectedStart() {
        task.setActiveRunId("rejected-run"); task.setLastCommandId("start-rejected");
        task.setDesiredStatus("RUNNING"); task.setActualStatus("FAILED");
        task.setErrorCode("MODEL_COMMAND_FAILED"); task.setErrorMessage("GatewayConflict");
        remember("rejected-run", "start-rejected", "FAILED");
    }

    @Test
    void stopAcknowledgementPinsNewRevisionForImmediateRestartWithoutHeartbeat() {
        service.applyCommandReport(ack("STOP_TASK", "stop-old", 4));
        assertThat(task.getActualStatus()).isEqualTo("STOPPED");
        assertThat(JsonUtils.parseMap(task.getMetricsSnapshot()).get("gatewayRevision")).isEqualTo(4);
        service.startTask(21L);
        verify(commands).createCommand(anyString(), eq(5L), eq("START_TASK"), eq(21L), eq(2),
                endsWith(":gateway:4"));
        assertThat(task.getParameters()).isEqualTo("{\"schemaVersion\":\"1.0\"}");
    }

    @Test
    void capacityRejectionDoesNotCreateRunCommandOrChangeProductionTaskState() {
        task.setActualStatus("STOPPED");
        task.setDesiredStatus("STOPPED");
        when(nodes.preflightTaskCapacity(eq(5L), eq(21L), anyCollection())).thenReturn(
                new com.linsight.module.aivideo.service.node.NodeTaskCapacityPreflightDTO(
                        false, "MODEL_CAPACITY_EXCEEDED",
                        "共享模型去重后需要 5/4 个模型槽位；冲突任务：任务 9 / 模型 130",
                        Map.of("allowed", false)));

        assertThatThrownBy(() -> service.startTask(21L))
                .isInstanceOf(ServiceException.class)
                .hasMessageContaining("任务 9");
        verify(runs, never()).insert(any(TaskRunDO.class));
        verify(commands, never()).createCommand(anyString(), anyLong(), eq("START_TASK"),
                anyLong(), anyInt(), anyString());
        verify(tasks, never()).claimStart(any());
        assertThat(task.getActualStatus()).isEqualTo("STOPPED");
        assertThat(task.getDesiredStatus()).isEqualTo("STOPPED");
    }

    @Test
    void startAcknowledgementPinsNewRevisionForImmediateStopWithoutHeartbeat() {
        task.setActiveRunId("new-run"); task.setLastCommandId("start-new");
        task.setActualStatus("STARTING"); task.setDesiredStatus("RUNNING");
        remember("new-run", "start-new", "STARTING");
        service.applyCommandReport(ack("START_TASK", "start-new", 5));
        service.stopTask(21L);
        verify(commands).createCommand(anyString(), eq(5L), eq("STOP_TASK"), eq(21L), eq(2),
                endsWith(":gateway:5"));
    }

    @Test
    void lateStopAcknowledgementCannotOverwriteANewerRun() {
        var report = ack("STOP_TASK", "stop-old", 4);
        task.setLastCommandId("start-new"); task.setActiveRunId("new-run"); task.setActualStatus("STARTING");
        service.applyCommandReport(report);
        verify(tasks, never()).updateRuntimeState(any());
        assertThat(task.getActualStatus()).isEqualTo("STARTING");
    }

    @Test
    void lateAcknowledgementCannotOverwriteNewerAutonomousRevision() {
        task.setMetricsSnapshot(JsonUtils.toJsonString(metrics(5))); task.setActualStatus("RUNNING");
        service.applyCommandReport(ack("STOP_TASK", "stop-old", 4));
        verify(tasks, never()).updateRuntimeState(any());
        assertThat(task.getActualStatus()).isEqualTo("RUNNING");
    }

    @Test
    void malformedResultCannotBecomeAuthoritativeGatewayState() {
        var report = ack("STOP_TASK", "stop-old", 4);
        report.setResult(Map.of("taskId", 999, "runId", "old-run", "configVersion", 2, "metrics", metrics(4)));
        service.applyCommandReport(report);
        verify(tasks, never()).updateRuntimeState(any());
    }

    @Test
    void newerRealGatewayRunRecoversARejectedStartAndAllowsNormalRetry() {
        rejectedStart();
        service.reportRuntime(5L, heartbeat("old-run", 4));
        assertThat(task.getActualStatus()).isEqualTo("STOPPED");
        assertThat(task.getDesiredStatus()).isEqualTo("RUNNING");
        assertThat(task.getActiveRunId()).isEqualTo("old-run");
        assertThat(task.getErrorCode()).isNull();
        service.startTask(21L);
        verify(commands).createCommand(anyString(), eq(5L), eq("START_TASK"), eq(21L), eq(2),
                endsWith(":gateway:4"));
    }

    @ParameterizedTest
    @ValueSource(strings = {"RUNNING", "STOPPED"})
    void newerFailedGatewayRunReplacesConflictAndAllowsStopRetry(String desiredStatus) {
        rejectedStart();
        task.setDesiredStatus(desiredStatus);
        var report = heartbeat("old-run", 4);
        report.setStatus("FAILED");
        report.setErrorCode("MODEL_CAPACITY_EXCEEDED");
        report.setErrorMessage("任务需要 5 个模型槽位，节点上限为 4");
        service.reportRuntime(5L, report);
        assertThat(task.getActiveRunId()).isEqualTo("old-run");
        assertThat(task.getActualStatus()).isEqualTo("FAILED");
        assertThat(task.getDesiredStatus()).isEqualTo(desiredStatus);
        assertThat(task.getErrorCode()).isEqualTo("MODEL_CAPACITY_EXCEEDED");
        assertThat(task.getErrorMessage()).contains("节点上限为 4");
        service.stopTask(21L);
        verify(commands).createCommand(anyString(), eq(5L), eq("STOP_TASK"), eq(21L), eq(2),
                endsWith(":gateway:4"));
    }

    @ParameterizedTest
    @ValueSource(strings = {"other-node", "stale-revision", "new-config", "pending-start", "model-failure", "not-platform-managed"})
    void recoveryDoesNotAcceptUnrelatedOrOutdatedHeartbeats(String invalid) {
        rejectedStart(); var report = heartbeat("old-run", 4); long node = 5;
        switch (invalid) {
            case "other-node" -> node = 1;
            case "stale-revision" -> report.setMetrics(metrics(3));
            case "new-config" -> report.setConfigVersion(1);
            case "pending-start" -> task.setActualStatus("STARTING");
            case "model-failure" -> task.setErrorMessage("model missing");
            case "not-platform-managed" -> report.setMetrics(Map.of("schemaVersion", "1.0", "gatewayRevision", 4));
        }
        long reporter = node;
        assertThatThrownBy(() -> service.reportRuntime(reporter, report)).isInstanceOf(ServiceException.class);
        assertThat(task.getActiveRunId()).isEqualTo("rejected-run");
        verify(tasks, never()).updateRuntimeState(any());
    }

    @Test
    void repeatedFailedStartReceiptCannotBreakRecoveredGatewayState() {
        rejectedStart();
        service.reportRuntime(5L, heartbeat("old-run", 4));
        var report = ack("START_TASK", "start-rejected", 4); report.setResult(null);
        report.setStatus("FAILED"); report.setErrorCode("MODEL_COMMAND_FAILED"); report.setErrorMessage("GatewayConflict");
        service.applyCommandReport(report);
        assertThat(task.getActualStatus()).isEqualTo("STOPPED");
        assertThat(task.getErrorCode()).isNull();
    }

    @Test
    void delayedHeartbeatCannotRollBackAcknowledgedRevision() {
        task.setMetricsSnapshot(JsonUtils.toJsonString(metrics(4)));
        assertThatThrownBy(() -> service.reportRuntime(5L, heartbeat("old-run", 3)))
                .isInstanceOf(ServiceException.class);
        verify(tasks, never()).updateRuntimeState(any());
    }

    @Test
    void conflictIsReportedAsTaskConfigurationConflictInsteadOfModelFailure() {
        rejectedStart();
        var report = ack("START_TASK", "start-rejected", 3); report.setResult(null);
        report.setStatus("FAILED"); report.setErrorCode("MODEL_COMMAND_FAILED"); report.setErrorMessage("GatewayConflict");
        service.applyCommandReport(report);
        assertThat(task.getErrorCode()).isEqualTo("TASK_GATEWAY_CONFLICT");
        assertThat(task.getErrorMessage()).contains("网关配置已更新");
    }

    @Test
    void settingsAcknowledgementUsesSettingsVersionInsteadOfLifecycleCommandId() {
        task.setGlobalSettingsVersion(7);
        var report = ack("APPLY_TASK_SETTINGS", "settings-7", 4);
        report.setIdempotencyKey("global-settings:7:task:21");
        service.applyCommandReport(report);
        assertThat(task.getAppliedGlobalSettingsVersion()).isEqualTo(7);
        assertThat(task.getLastCommandId()).isEqualTo("stop-old");
        assertThat(JsonUtils.parseMap(task.getMetricsSnapshot()).get("gatewayRevision")).isEqualTo(4);
    }
}
