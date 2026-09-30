package com.linsight.module.aivideo.dal.mysql.task;

import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.linsight.framework.common.pojo.PageParam;
import com.linsight.framework.common.pojo.PageResult;
import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.linsight.module.aivideo.dal.dataobject.task.TaskDO;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Param;

import java.util.List;

@Mapper
public interface TaskMapper extends BaseMapperX<TaskDO> {
    /** Serialize lifecycle commands with their acknowledgements and gateway heartbeats. */
    default TaskDO selectByIdForUpdate(Long id) {
        return selectOne(new LambdaQueryWrapperX<TaskDO>()
                .eq(TaskDO::getId, id).last("FOR UPDATE"));
    }

    /**
     * Persist the complete runtime state, including nullable fields that intentionally clear
     * diagnostics or the active run. MyBatis' default NOT_NULL strategy would otherwise leave
     * stale failure details on a recovered task.
     */
    default int updateRuntimeState(TaskDO task) {
        return update(null, new LambdaUpdateWrapper<TaskDO>()
                .eq(TaskDO::getId, task.getId())
                .set(TaskDO::getDesiredStatus, task.getDesiredStatus())
                .set(TaskDO::getActualStatus, task.getActualStatus())
                .set(TaskDO::getActiveRunId, task.getActiveRunId())
                .set(TaskDO::getLastCommandId, task.getLastCommandId())
                .set(TaskDO::getLastHeartbeatTime, task.getLastHeartbeatTime())
                .set(TaskDO::getMetricsSnapshot, task.getMetricsSnapshot())
                .set(TaskDO::getDiagnosticId, task.getDiagnosticId())
                .set(TaskDO::getErrorCode, task.getErrorCode())
                .set(TaskDO::getErrorMessage, task.getErrorMessage())
                .set(TaskDO::getGlobalSettingsVersion, task.getGlobalSettingsVersion())
                .set(TaskDO::getAppliedGlobalSettingsVersion, task.getAppliedGlobalSettingsVersion())
                .set(TaskDO::getGlobalSettingsSnapshot, task.getGlobalSettingsSnapshot()));
    }

    default int claimStart(TaskDO task) {
        return update(null, new LambdaUpdateWrapper<TaskDO>()
                .eq(TaskDO::getId, task.getId()).eq(TaskDO::getConfigVersion, task.getConfigVersion())
                .in(TaskDO::getActualStatus, List.of("DRAFT", "STOPPED", "FAILED", "OFFLINE"))
                .set(TaskDO::getDesiredStatus, "RUNNING").set(TaskDO::getActualStatus, "STARTING")
                .set(TaskDO::getActiveRunId, task.getActiveRunId()).set(TaskDO::getLastCommandId, task.getLastCommandId())
                .set(TaskDO::getDiagnosticId, null).set(TaskDO::getErrorCode, null).set(TaskDO::getErrorMessage, null));
    }

    default int updateRuleVersion(Long id, Integer expectedVersion, Long ruleId, Long ruleVersionId) {
        return update(null, new LambdaUpdateWrapper<TaskDO>()
                .eq(TaskDO::getId, id).eq(TaskDO::getConfigVersion, expectedVersion)
                .eq(TaskDO::getDesiredStatus, "STOPPED")
                .in(TaskDO::getActualStatus, List.of("DRAFT", "STOPPED"))
                .set(TaskDO::getRuleId, ruleId).set(TaskDO::getRuleVersionId, ruleVersionId)
                .set(TaskDO::getConfigVersion, expectedVersion + 1));
    }

    /** Tenant interceptor also scopes this tombstone lookup; prevent retries resurrecting removed assignments. */
    @Select("SELECT COUNT(*) FROM ai_task WHERE code = #{code} AND deleted = 1")
    long countDeletedByCode(@Param("code") String code);

    default List<TaskDO> selectByCameraAndAlgorithm(Long cameraId, Long algorithmId) {
        return selectList(new LambdaQueryWrapperX<TaskDO>()
                .eq(TaskDO::getCameraId, cameraId).eq(TaskDO::getAlgorithmId, algorithmId)
                .orderByAsc(TaskDO::getId));
    }

    default TaskDO selectByCode(String code) {
        return selectOne(TaskDO::getCode, code);
    }

    default PageResult<TaskDO> selectPage(PageParam pageParam, String name, String code, Long cameraId,
                                           Long algorithmId, Long nodeId, String actualStatus) {
        return selectPage(pageParam, new LambdaQueryWrapperX<TaskDO>()
                .likeIfPresent(TaskDO::getName, name)
                .likeIfPresent(TaskDO::getCode, code)
                .eqIfPresent(TaskDO::getCameraId, cameraId)
                .eqIfPresent(TaskDO::getAlgorithmId, algorithmId)
                .eqIfPresent(TaskDO::getNodeId, nodeId)
                .eqIfPresent(TaskDO::getActualStatus, actualStatus)
                .orderByDesc(TaskDO::getId));
    }

    default List<TaskDO> selectRunning(List<Long> taskIds) {
        LambdaQueryWrapperX<TaskDO> query = new LambdaQueryWrapperX<>();
        query.in(TaskDO::getActualStatus, List.of("STARTING", "RUNNING"));
        query.orderByAsc(TaskDO::getId);
        if (taskIds != null) {
            if (taskIds.isEmpty()) return List.of();
            query.in(TaskDO::getId, taskIds);
        }
        return selectList(query);
    }

    default boolean existsByNodeId(Long nodeId) {
        return selectCount(TaskDO::getNodeId, nodeId) > 0;
    }
}
