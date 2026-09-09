package com.linsight.module.aivideo.service.task;

import com.linsight.framework.common.exception.ServiceException;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.module.aivideo.controller.admin.task.vo.TaskSaveReqVO;
import com.linsight.module.aivideo.dal.dataobject.algorithm.AlgorithmDO;
import com.linsight.module.aivideo.dal.dataobject.algorithm.PipelineVersionDO;
import com.linsight.module.aivideo.dal.dataobject.camera.CameraDO;
import com.linsight.module.aivideo.dal.dataobject.model.ModelVersionDO;
import com.linsight.module.aivideo.dal.mysql.task.TaskMapper;
import com.linsight.module.aivideo.dal.dataobject.task.TaskDO;
import org.springframework.beans.BeanUtils;
import com.linsight.module.aivideo.service.algorithm.AlgorithmService;
import com.linsight.module.aivideo.service.camera.CameraService;
import com.linsight.module.aivideo.service.model.ModelExecutionService;
import com.linsight.module.aivideo.service.model.ModelService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class TaskValidationModeTest {
    @Mock private TaskMapper taskMapper;
    @Mock private CameraService cameraService;
    @Mock private AlgorithmService algorithmService;
    @Mock private ModelService modelService;
    @Mock private ModelExecutionService modelExecutionService;
    @InjectMocks private TaskServiceImpl service;

    private TaskSaveReqVO request(Object mode) {
        CameraDO camera = new CameraDO();
        camera.setStatus(0);
        when(cameraService.getCamera(2L)).thenReturn(camera);
        AlgorithmDO algorithm = new AlgorithmDO();
        algorithm.setStatus(0);
        algorithm.setDefaultModelId(71014L);
        when(algorithmService.getAlgorithm(72001L)).thenReturn(algorithm);
        PipelineVersionDO pipeline = new PipelineVersionDO();
        pipeline.setId(82621L);
        pipeline.setDag(JsonUtils.toJsonString(Map.of("nodes", List.of(), "acceptance", Map.of("status", "PENDING"))));
        when(algorithmService.getPublishedPipeline(72001L, 82621L)).thenReturn(pipeline);
        TaskSaveReqVO request = new TaskSaveReqVO();
        request.setCode("field-validation-test");
        request.setCameraId(2L);
        request.setAlgorithmId(72001L);
        request.setPipelineVersionId(82621L);
        request.setModelVersionId(119L);
        request.setNodeId(1L);
        request.setParameters(Map.of("schemaVersion", "1.0", "validationOnly", mode));
        return request;
    }

    @Test
    void validationStillRequiresReadyDeploymentOnTheSelectedNode() {
        TaskSaveReqVO request = request(true);
        ModelVersionDO version = new ModelVersionDO();
        version.setModelId(71014L);
        version.setPublishStatus("PUBLISHED");
        version.setExecutionStatus("READY");
        when(modelService.getVersion(119L)).thenReturn(version);
        doThrow(new ServiceException(400, "deployment not ready"))
                .when(modelExecutionService).validateDeploymentReady(119L, 1L);
        TaskDO task = new TaskDO();
        BeanUtils.copyProperties(request, task, "parameters", "modelBindings");
        task.setActualStatus("DRAFT");
        task.setParameters(JsonUtils.toJsonString(request.getParameters()));
        when(taskMapper.selectById(2L)).thenReturn(task);
        assertThrows(ServiceException.class, () -> service.startTask(2L));
        verify(algorithmService).validatePipelineRunnable(any(PipelineVersionDO.class), org.mockito.ArgumentMatchers.eq(true));
        verify(taskMapper, never()).insert(any(com.linsight.module.aivideo.dal.dataobject.task.TaskDO.class));
    }

    @Test
    void validationFlagCannotBeAString() {
        TaskSaveReqVO request = request("true");
        assertThrows(ServiceException.class, () -> service.createTask(request));
        verify(algorithmService, never()).validatePipelineRunnable(any(PipelineVersionDO.class), anyBoolean());
    }
}
