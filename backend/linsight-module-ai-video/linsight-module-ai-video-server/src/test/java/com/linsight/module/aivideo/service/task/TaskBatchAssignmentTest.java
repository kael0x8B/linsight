package com.linsight.module.aivideo.service.task;

import com.linsight.framework.common.exception.ServiceException;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.module.aivideo.controller.admin.task.vo.TaskBatchCreateReqVO;
import com.linsight.module.aivideo.controller.admin.settings.vo.GlobalSettingsRespVO;
import com.linsight.module.aivideo.dal.dataobject.algorithm.AlgorithmDO;
import com.linsight.module.aivideo.dal.dataobject.algorithm.PipelineVersionDO;
import com.linsight.module.aivideo.dal.dataobject.camera.CameraDO;
import com.linsight.module.aivideo.dal.dataobject.model.ModelVersionDO;
import com.linsight.module.aivideo.dal.dataobject.task.TaskDO;
import com.linsight.module.aivideo.dal.mysql.task.TaskMapper;
import com.linsight.module.aivideo.service.algorithm.AlgorithmService;
import com.linsight.module.aivideo.service.camera.CameraService;
import com.linsight.module.aivideo.service.model.ModelExecutionService;
import com.linsight.module.aivideo.service.model.ModelService;
import com.linsight.module.aivideo.service.node.NodeService;
import com.linsight.module.aivideo.service.rule.RuleService;
import com.linsight.module.aivideo.service.rule.RuleVersionConfigDTO;
import com.linsight.module.aivideo.service.settings.GlobalSettingsService;
import jakarta.validation.Validation;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.dao.DuplicateKeyException;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class TaskBatchAssignmentTest {
    @Mock TaskMapper tasks;
    @Mock CameraService cameras;
    @Mock AlgorithmService algorithms;
    @Mock ModelService models;
    @Mock ModelExecutionService execution;
    @Mock NodeService nodes;
    @Mock RuleService rules;
    @Mock GlobalSettingsService settings;
    @InjectMocks TaskServiceImpl service;

    private TaskBatchCreateReqVO request(Long... cameraIds) {
        var request = new TaskBatchCreateReqVO();
        request.setRequestId("acc8a1c3-e29b-4210-b0b0-29097c248fe5");
        request.setCameraIds(List.of(cameraIds));
        request.setAlgorithmId(3L);
        request.setModelVersionId(4L);
        request.setNodeId(5L);
        request.setParameters(Map.of("schemaVersion", "1.0", "validationOnly", true));
        return request;
    }

    private TaskDO existing(Long id, Long cameraId, String status) {
        var task = new TaskDO(); task.setId(id); task.setCameraId(cameraId);
        task.setAlgorithmId(3L); task.setActualStatus(status); return task;
    }

    private void readyDraft(Long cameraId) {
        var camera = new CameraDO(); camera.setStatus(0);
        when(cameras.getCamera(cameraId)).thenReturn(camera);
        var algorithm = new AlgorithmDO(); algorithm.setStatus(0); algorithm.setDefaultModelId(6L);
        when(algorithms.getAlgorithm(3L)).thenReturn(algorithm);
        var pipeline = new PipelineVersionDO(); pipeline.setId(7L);
        pipeline.setDag(JsonUtils.toJsonString(Map.of("nodes", List.of())));
        when(algorithms.getPublishedPipeline(3L, null)).thenReturn(pipeline);
        var version = new ModelVersionDO(); version.setModelId(6L);
        version.setPublishStatus("PUBLISHED"); version.setExecutionStatus("READY");
        when(models.getVersion(4L)).thenReturn(version);
        var global = new GlobalSettingsRespVO(1, new com.linsight.module.aivideo.controller.admin.settings.vo.AiGlobalSettingsVO()); when(settings.getCurrent()).thenReturn(global);
    }

    @Test void existingCameraIsNotModifiedAndFailureDoesNotAbortLaterCameras() {
        when(tasks.selectByCameraAndAlgorithm(1L, 3L)).thenReturn(List.of(existing(11L, 1L, "RUNNING")));
        when(cameras.getCamera(2L)).thenThrow(new ServiceException(400, "camera disabled"));
        readyDraft(3L);
        doAnswer(call -> { ((TaskDO) call.getArgument(0)).setId(13L); return 1; }).when(tasks).insert(any(TaskDO.class));
        var result = service.batchCreateTasks(request(1L, 2L, 3L, 3L));
        assertThat(result).extracting(item -> item.status()).containsExactly("UNCHANGED", "FAILED", "CREATED");
        assertThat(result.get(0).actualStatus()).isEqualTo("RUNNING");
        assertThat(result.get(2).taskId()).isEqualTo(13L);
        verify(tasks, never()).updateById(any(TaskDO.class));
        verify(tasks, times(1)).insert(any(TaskDO.class));
        verify(nodes).validateNodeExists(5L);
        verify(nodes, never()).validateNodeAvailable(anyLong());
        verifyNoInteractions(execution);
    }

    @Test void requestReplayUsesOriginalTaskAndCannotChangeAlgorithm() {
        var saved = existing(12L, 2L, "STOPPED");
        when(tasks.selectByCode(anyString())).thenReturn(saved);
        assertThat(service.batchCreateTasks(request(2L)).get(0).taskId()).isEqualTo(12L);
        var other = request(2L); other.setAlgorithmId(9L);
        assertThat(service.batchCreateTasks(other).get(0).status()).isEqualTo("FAILED");
        verify(tasks, never()).insert(any(TaskDO.class));
        verifyNoInteractions(cameras, models, nodes);
    }

    @Test void retryMustNotResurrectAnAssignmentThatWasRemoved() {
        when(tasks.countDeletedByCode(anyString())).thenReturn(1L);
        assertThat(service.batchCreateTasks(request(2L)).get(0).status()).isEqualTo("FAILED");
        verify(tasks, never()).insert(any(TaskDO.class));
        verifyNoInteractions(cameras, models, nodes);
    }

    @Test void concurrentRetryFindsTheCommittedTaskAfterUniqueCodeConflict() {
        readyDraft(2L);
        var saved = existing(12L, 2L, "DRAFT");
        when(tasks.selectByCode(anyString())).thenReturn(null, null, saved);
        when(tasks.insert(any(TaskDO.class))).thenThrow(new DuplicateKeyException("same request"));
        var result = service.batchCreateTasks(request(2L)).get(0);
        assertThat(result.status()).isEqualTo("CREATED");
        assertThat(result.taskId()).isEqualTo(12L);
    }

    @Test void copiedRegionsNeedExplicitConfirmation() {
        var request = request(2L); request.setRuleId(8L); request.setRuleVersionId(9L);
        when(rules.getPublishedRuleConfig(8L, 9L)).thenReturn(new RuleVersionConfigDTO(8L, 9L, 1, "SAFETY_HELMET",
                Map.of("regions", List.of(Map.of("id", "door")))));
        assertThat(service.batchCreateTasks(request).get(0).status()).isEqualTo("FAILED");
        verify(tasks, never()).insert(any(TaskDO.class));
    }

    @Test void activeOrUnconfirmedTaskCannotBeRemoved() {
        for (String state : List.of("RUNNING", "STARTING", "STOPPING", "FAILED", "OFFLINE")) {
            when(tasks.selectById(2L)).thenReturn(existing(2L, 2L, state));
            assertThatThrownBy(() -> service.deleteTask(2L)).isInstanceOf(ServiceException.class);
        }
        verify(tasks, never()).deleteById(anyLong());
    }

    @Test void batchLimitAndNestedConfigurationValidationAreEnforced() {
        try (var factory = Validation.buildDefaultValidatorFactory()) {
            var validator = factory.getValidator();
            assertThat(validator.validate(request(1L))).isEmpty();
            var invalid = request(0L); invalid.setRequestId("unsafe"); invalid.setNodeId(null);
            assertThat(validator.validate(invalid)).hasSize(3);
            invalid = request(1L); invalid.setCameraIds(java.util.Collections.nCopies(101, 1L));
            assertThat(validator.validate(invalid)).hasSize(1);
        }
    }
}
