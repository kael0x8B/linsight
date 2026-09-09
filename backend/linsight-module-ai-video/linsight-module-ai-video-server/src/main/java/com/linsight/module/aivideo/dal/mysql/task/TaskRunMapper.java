package com.linsight.module.aivideo.dal.mysql.task;

import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.linsight.module.aivideo.dal.dataobject.task.TaskRunDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

@Mapper
public interface TaskRunMapper extends BaseMapperX<TaskRunDO> {
    default TaskRunDO selectByRunId(String runId) {
        return selectOne(TaskRunDO::getRunId, runId);
    }

    default TaskRunDO selectByCommandId(String commandId) {
        return selectOne(TaskRunDO::getCommandId, commandId);
    }

    default List<TaskRunDO> selectListByTask(Long taskId) {
        return selectList(new LambdaQueryWrapperX<TaskRunDO>()
                .eq(TaskRunDO::getTaskId, taskId)
                .orderByDesc(TaskRunDO::getId)
                .last("LIMIT 50"));
    }
}
