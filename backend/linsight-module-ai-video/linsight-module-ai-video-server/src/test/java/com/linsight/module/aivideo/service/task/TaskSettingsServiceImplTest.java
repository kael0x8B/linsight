package com.linsight.module.aivideo.service.task;

import com.linsight.module.aivideo.dal.dataobject.task.TaskDO;
import com.linsight.module.aivideo.dal.mysql.task.TaskMapper;
import com.linsight.module.aivideo.service.node.NodeCommandService;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class TaskSettingsServiceImplTest {
    @Test
    void grayApplyShouldSnapshotVersionAndCreateDurableCommand() {
        TaskMapper taskMapper = mock(TaskMapper.class);
        NodeCommandService commandService = mock(NodeCommandService.class);
        TaskDO task = new TaskDO();
        task.setId(7L);
        task.setNodeId(9L);
        task.setConfigVersion(3);
        when(taskMapper.selectRunning(List.of(7L))).thenReturn(List.of(task));
        TaskSettingsServiceImpl service = new TaskSettingsServiceImpl();
        ReflectionTestUtils.setField(service, "taskMapper", taskMapper);
        ReflectionTestUtils.setField(service, "nodeCommandService", commandService);

        TaskSettingsService.ApplyResult result = service.apply(4, "{\"schemaVersion\":\"1.0\"}",
                "GRAY", List.of(7L));

        assertThat(result.affectedTaskCount()).isEqualTo(1);
        assertThat(result.commandCount()).isEqualTo(1);
        assertThat(task.getGlobalSettingsVersion()).isEqualTo(4);
        verify(commandService).createCommand(anyString(), eq(9L), eq("APPLY_TASK_SETTINGS"),
                eq(7L), eq(3), eq("global-settings:4:task:7"));
    }
}
