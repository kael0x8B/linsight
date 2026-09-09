package com.linsight.module.aivideo.service.task;

import com.linsight.framework.common.pojo.PageResult;
import com.linsight.module.aivideo.controller.admin.task.vo.TaskPageReqVO;
import com.linsight.module.aivideo.controller.admin.task.vo.TaskSaveReqVO;
import com.linsight.module.aivideo.controller.admin.task.vo.TaskRuleUpdateReqVO;
import com.linsight.module.aivideo.controller.admin.task.vo.TaskBatchCreateReqVO;
import com.linsight.module.aivideo.controller.admin.task.vo.TaskBatchResultRespVO;
import com.linsight.module.aivideo.controller.node.task.vo.TaskCommandDetailRespVO;
import com.linsight.module.aivideo.controller.node.task.vo.TaskRuntimeReportReqVO;
import com.linsight.module.aivideo.dal.dataobject.task.TaskDO;
import com.linsight.module.aivideo.dal.dataobject.task.TaskRunDO;
import com.linsight.module.aivideo.service.node.NodeCommandDTO;

import java.util.List;

public interface TaskService {
    /** Tenant-scoped display names only; credentials and domain entities never cross this query contract. */
    java.util.Map<Long, String> getTaskNames(java.util.Collection<Long> ids);
    List<TaskCameraCapabilityDTO> getCameraCapabilities(java.util.Collection<Long> cameraIds);
    java.util.Map<Long, Long> getNodeCounts(java.util.Collection<Long> nodeIds);
    Long createTask(TaskSaveReqVO reqVO);
    List<TaskBatchResultRespVO> batchCreateTasks(TaskBatchCreateReqVO reqVO);
    void updateTask(TaskSaveReqVO reqVO);

    void updateTaskRule(TaskRuleUpdateReqVO reqVO);
    void deleteTask(Long id);
    TaskDO getTask(Long id);
    PageResult<TaskDO> getTaskPage(TaskPageReqVO reqVO);
    List<TaskRunDO> getRuns(Long taskId);
    String startTask(Long id);
    String stopTask(Long id);
    TaskCommandDetailRespVO getCommandDetail(String commandId, Long nodeId);
    void applyCommandReport(NodeCommandDTO report);
    void reportRuntime(Long nodeId, TaskRuntimeReportReqVO reqVO);
    void validateRuntimeOverlay(Long nodeId, Long taskId, String runId, Long cameraId);
    boolean hasTasksForNode(Long nodeId);
}
