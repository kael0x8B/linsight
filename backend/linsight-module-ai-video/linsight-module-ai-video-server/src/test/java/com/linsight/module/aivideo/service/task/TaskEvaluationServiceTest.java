package com.linsight.module.aivideo.service.task;

import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.module.aivideo.controller.admin.task.vo.TaskEvaluationCreateReqVO;
import com.linsight.module.aivideo.dal.dataobject.task.TaskDO;
import com.linsight.module.aivideo.dal.dataobject.task.TaskEvaluationDO;
import com.linsight.module.aivideo.dal.mysql.task.TaskEvaluationMapper;
import com.linsight.module.aivideo.dal.mysql.task.TaskMapper;
import com.linsight.module.aivideo.service.algorithm.*;
import com.linsight.module.aivideo.service.model.*;
import com.linsight.module.aivideo.service.node.*;
import com.linsight.module.aivideo.service.rule.RuleService;
import jakarta.validation.Validation;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.math.BigDecimal;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

class TaskEvaluationServiceTest {
    final TaskEvaluationServiceImpl service = new TaskEvaluationServiceImpl();
    final TaskMapper tasks = mock(TaskMapper.class);
    final TaskEvaluationMapper records = mock(TaskEvaluationMapper.class);
    final AlgorithmService algorithms = mock(AlgorithmService.class);
    final ModelService models = mock(ModelService.class);
    final NodeService nodes = mock(NodeService.class);
    final RuleService rules = mock(RuleService.class);
    final TaskDO task = new TaskDO();
    final AtomicReference<TaskEvaluationDO> saved = new AtomicReference<>();

    TaskEvaluationServiceTest() {
        ReflectionTestUtils.setField(service, "taskMapper", tasks);
        ReflectionTestUtils.setField(service, "evaluationMapper", records);
        ReflectionTestUtils.setField(service, "algorithmService", algorithms);
        ReflectionTestUtils.setField(service, "modelService", models);
        ReflectionTestUtils.setField(service, "nodeService", nodes);
        ReflectionTestUtils.setField(service, "ruleService", rules);
        task.setId(1L); task.setName("评测任务"); task.setConfigVersion(3);
        task.setAlgorithmId(2L); task.setPipelineVersionId(7L); task.setModelVersionId(11L);
        task.setNodeId(5L); task.setCameraId(6L); task.setParameters("{\"sampleFps\":2}");
        task.setModelBindings("{\"person\":11}");
        when(tasks.selectByIdForUpdate(1L)).thenReturn(task);
        when(algorithms.getEvaluationSnapshot(2L, 7L)).thenReturn(new AlgorithmEvaluationSnapshotDTO(
                2L, 7L, 1, Map.of("algorithmPackage", Map.of("sha256", "b".repeat(64)))));
        when(models.getEvaluationSnapshot(11L)).thenReturn(new ModelEvaluationSnapshotDTO(
                10L, 11L, "1.0", "a".repeat(64), "ONNX", "{}"));
        when(nodes.getEvaluationSnapshot(5L)).thenReturn(new NodeEvaluationSnapshotDTO(
                5L, "离线节点", "0.1", 0, null, NodeModelEnvironmentDTO.unknown()));
        doAnswer(invocation -> { var record = (TaskEvaluationDO) invocation.getArgument(0);
            record.setId(42L); saved.set(record); return 1;
        }).when(records).insert(any(TaskEvaluationDO.class));
    }

    static TaskEvaluationCreateReqVO request() {
        return JsonUtils.parseObject("""
            {"requestId":"evaluation-request-0001","taskId":1,"expectedConfigVersion":3,"expectedGatewayRevision":0,
             "measuredAtMillis":1700000000000,"datasetVersion":"video-v1",
             "datasetSha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
             "evidenceRef":"reports/run-1.json","environmentDescription":"CPU / fixture test",
             "cooldownDedupPass":true,
             "metrics":{"eventPrecision":0.9,"eventRecall":0.9,"falsePositivesPerStreamHour":1,
               "missedEvents":0,"endToEndP95Ms":1500,"averageFps":1},
             "thresholds":{"minEventPrecision":0.9,"minEventRecall":0.9,"maxFalsePositivesPerStreamHour":1,
               "maxMissedEvents":0,"maxEndToEndP95Ms":1500,"minAverageFps":1},
             "resourceUsage":{"cpuPeakPercent":20,"memoryPeakMiB":100,"acceleratorMemoryPeakMiB":0}}
            """, TaskEvaluationCreateReqVO.class);
    }

    @Test void passIsIndependentAndUsesSelectedPackageVersionEvenOnOfflineNode() {
        assertThat(service.create(request())).isEqualTo(42);
        var record = saved.get();
        assertThat(record.getStatus()).isEqualTo("PASS");
        assertThat(record.getSource()).isEqualTo("MANUAL_VIDEO");
        var snapshot = JsonUtils.parseMap(record.getConfigurationSnapshot());
        assertThat(((Map<?, ?>) snapshot.get("pipeline")).get("pipelineVersionId")).isEqualTo(7);
        assertThat(record.getConfigurationSnapshot()).contains("modelVersionId", "sha256", "sampleFps", "nodeAtRecording");
        verify(algorithms).getEvaluationSnapshot(2L, 7L);
        verifyNoMoreInteractions(algorithms); // Must never create/validate/publish a Pipeline.
        verify(tasks, never()).updateById(any(TaskDO.class));
        task.setParameters("{\"sampleFps\":99}");
        assertThat(record.getConfigurationSnapshot()).doesNotContain("99");
    }

    @Test void slowAndZeroFpsMeasurementsAreValidFailedEvidence() {
        var request = request();
        request.getMetrics().setEndToEndP95Ms(new BigDecimal("8500"));
        request.getMetrics().setAverageFps(BigDecimal.ZERO);
        request.setCooldownDedupPass(false);
        service.create(request);
        assertThat(saved.get().getStatus()).isEqualTo("FAIL");
        assertThat(saved.get().getFailedChecks()).contains("endToEndP95Ms", "averageFps", "cooldownDedup");
    }

    @Test void idempotentRetryReturnsSameImmutableRecordAndRejectsChangedBody() {
        var request = request();
        service.create(request);
        when(records.selectByRequest(1L, request.getRequestId())).thenReturn(saved.get());
        task.setConfigVersion(4); // A lost response can be retried after the task moves on.
        assertThat(service.create(request)).isEqualTo(42);
        request.setNote("changed");
        assertThatThrownBy(() -> service.create(request)).hasMessageContaining("不同内容");
        verify(records, times(1)).insert(any(TaskEvaluationDO.class));
    }

    @Test void staleConfigurationOrMissingTenantScopedTaskCannotProduceEvidence() {
        task.setConfigVersion(4);
        assertThatThrownBy(() -> service.create(request())).hasMessageContaining("配置已改变");
        when(tasks.selectByIdForUpdate(1L)).thenReturn(null);
        assertThatThrownBy(() -> service.create(request())).hasMessageContaining("任务不存在");
        verifyNoInteractions(algorithms, models, nodes);
        verify(records, never()).insert(any(TaskEvaluationDO.class));
    }

    @Test void requestValidationRejectsMissingInvalidAndSignedEvidence() {
        try (var factory = Validation.buildDefaultValidatorFactory()) {
            var validator = factory.getValidator();
            var request = request();
            assertThat(validator.validate(request)).isEmpty();
            request.getMetrics().setEventPrecision(new BigDecimal("1.1"));
            request.getMetrics().setMissedEvents(-1);
            request.setEvidenceRef("https://storage/report?token=secret");
            request.setEnvironmentDescription(" ");
            assertThat(validator.validate(request)).hasSize(4);
            request.setMetrics(null);
            assertThat(validator.validate(request)).anyMatch(v -> v.getPropertyPath().toString().equals("metrics"));
        }
    }

    @Test void futureMeasurementIsRejected() {
        var request = request(); request.setMeasuredAtMillis(System.currentTimeMillis() + 3_600_000);
        assertThatThrownBy(() -> service.create(request)).hasMessageContaining("未来");
        verify(records, never()).insert(any(TaskEvaluationDO.class));
    }

    @Test void gatewayRevisionPreventsMisattributionAndKeepsEffectiveConfiguration() {
        task.setMetricsSnapshot("""
            {"gatewayRevision":6,"gatewayAppliedRevision":6,"gatewayPlatformManaged":true,
             "gatewayConfiguration":{"taskId":1,"cameraId":6,"algorithmId":2,"pipelineVersionId":7,
               "configVersion":3,"modelVersionId":12,"modelBindings":{"person":12},
               "parameters":{"sampleFps":4},"rule":{"schemaVersion":"1.0"},
               "sourceUrl":"rtsp://private-camera"}}
            """);
        var request = request();
        assertThatThrownBy(() -> service.create(request)).hasMessageContaining("配置已改变");
        request.setExpectedGatewayRevision(6L);
        when(models.getEvaluationSnapshot(12L)).thenReturn(new ModelEvaluationSnapshotDTO(
                10L, 12L, "2.0", "c".repeat(64), "ONNX", "{}"));
        service.create(request);
        assertThat(saved.get().getConfigurationSnapshot()).contains("GATEWAY_REPORTED_AT_RECORDING", "gatewayRevision", "2.0")
                .doesNotContain("rtsp://", "private-camera", "sourceUrl");
        verify(models).getEvaluationSnapshot(12L);
        verify(models, never()).getEvaluationSnapshot(11L);
    }
}
