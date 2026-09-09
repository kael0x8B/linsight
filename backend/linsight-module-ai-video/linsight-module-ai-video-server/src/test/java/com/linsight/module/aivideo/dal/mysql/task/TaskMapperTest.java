package com.linsight.module.aivideo.dal.mysql.task;

import com.baomidou.mybatisplus.core.conditions.Wrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.baomidou.mybatisplus.core.MybatisConfiguration;
import com.baomidou.mybatisplus.core.metadata.TableInfoHelper;
import com.linsight.module.aivideo.dal.dataobject.task.TaskDO;
import org.apache.ibatis.builder.MapperBuilderAssistant;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.CALLS_REAL_METHODS;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

class TaskMapperTest {

    @BeforeAll
    static void initializeTableMetadata() {
        TableInfoHelper.initTableInfo(
                new MapperBuilderAssistant(new MybatisConfiguration(), "task-mapper-test"),
                TaskDO.class);
    }

    @Test
    @SuppressWarnings("unchecked")
    void runtimeStateUpdateMustWriteNullableRecoveryFields() {
        TaskMapper mapper = mock(TaskMapper.class, CALLS_REAL_METHODS);
        TaskDO task = new TaskDO();
        task.setId(1L);
        task.setDesiredStatus("RUNNING");
        task.setActualStatus("RUNNING");
        task.setActiveRunId("run-1");
        task.setErrorCode(null);
        task.setErrorMessage(null);

        mapper.updateRuntimeState(task);

        ArgumentCaptor<Wrapper<TaskDO>> wrapperCaptor = ArgumentCaptor.forClass(Wrapper.class);
        verify(mapper).update(isNull(), wrapperCaptor.capture());
        String sqlSet = ((LambdaUpdateWrapper<TaskDO>) wrapperCaptor.getValue()).getSqlSet();
        assertTrue(sqlSet.contains("active_run_id"));
        assertTrue(sqlSet.contains("diagnostic_id"));
        assertTrue(sqlSet.contains("error_code"));
        assertTrue(sqlSet.contains("error_message"));
    }
}
