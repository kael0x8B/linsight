package com.linsight.module.aivideo.dal.mysql.task;

import com.linsight.framework.common.pojo.PageResult;
import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.linsight.framework.common.pojo.PageParam;
import com.linsight.module.aivideo.dal.dataobject.task.TaskEvaluationDO;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface TaskEvaluationMapper extends BaseMapperX<TaskEvaluationDO> {
    default TaskEvaluationDO selectByRequest(Long taskId, String requestId) {
        return selectOne(new LambdaQueryWrapperX<TaskEvaluationDO>()
                .eq(TaskEvaluationDO::getTaskId, taskId).eq(TaskEvaluationDO::getRequestId, requestId));
    }
    default PageResult<TaskEvaluationDO> selectPage(PageParam request, Long taskId, String status) {
        return selectPage(request, new LambdaQueryWrapperX<TaskEvaluationDO>()
                .eqIfPresent(TaskEvaluationDO::getTaskId, taskId)
                .eqIfPresent(TaskEvaluationDO::getStatus, status)
                .orderByDesc(TaskEvaluationDO::getId));
    }
}
