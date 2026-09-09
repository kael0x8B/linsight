package com.linsight.module.aivideo.service.task;

import com.linsight.module.aivideo.dal.dataobject.task.TaskDO;
import com.linsight.module.aivideo.dal.mysql.task.TaskMapper;
import com.linsight.module.aivideo.service.node.NodeCommandDTO;
import com.linsight.module.aivideo.service.node.NodeCommandService;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.TransactionCallback;
import org.springframework.transaction.support.TransactionTemplate;

import static com.linsight.framework.common.exception.util.ServiceExceptionUtil.exception;
import static com.linsight.module.aivideo.enums.node.ErrorCodeConstants.NODE_COMMAND_NOT_FOUND;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class TaskStopRetryTest {
    private final TaskMapper tasks = mock(TaskMapper.class);
    private final NodeCommandService commands = mock(NodeCommandService.class);
    private final TransactionTemplate transactions = mock(TransactionTemplate.class);
    private final TaskServiceImpl service = new TaskServiceImpl();
    private final TaskDO task = new TaskDO();

    TaskStopRetryTest() {
        ReflectionTestUtils.setField(service, "taskMapper", tasks);
        ReflectionTestUtils.setField(service, "nodeCommandService", commands);
        ReflectionTestUtils.setField(service, "transactionTemplate", transactions);
        task.setId(2L);
        task.setNodeId(1L);
        task.setConfigVersion(3);
        task.setActiveRunId("run-a");
        task.setLastCommandId("previous-command");
        when(tasks.selectById(2L)).thenReturn(task);
        when(transactions.execute(any())).thenAnswer(call ->
                ((TransactionCallback<?>) call.getArgument(0)).doInTransaction(mock(TransactionStatus.class)));
        when(commands.createCommand(anyString(), eq(1L), eq("STOP_TASK"), eq(2L), eq(3), anyString()))
                .thenReturn("durable-command");
    }

    @Test
    void failedStopGetsNewAttemptAndStoresTheActualDeduplicatedId() {
        task.setActualStatus("FAILED");
        task.setErrorCode("MODEL_COMMAND_FAILED");
        assertThat(service.stopTask(2L)).isEqualTo("durable-command");
        assertThat(task.getLastCommandId()).isEqualTo("durable-command");
        assertThat(task.getActualStatus()).isEqualTo("STOPPING");
        assertThat(task.getErrorCode()).isNull();
        verify(commands).createCommand(anyString(), eq(1L), eq("STOP_TASK"), eq(2L), eq(3),
                eq("task-stop:2:run-a:previous-command:gateway:0"));
        verify(tasks).updateRuntimeState(task);
    }

    @Test
    void stopPinsTheObservedGatewayRevisionBeforeDispatch() {
        task.setActualStatus("RUNNING");
        task.setMetricsSnapshot("{\"gatewayRevision\":17}");
        service.stopTask(2L);
        verify(commands).createCommand(anyString(), eq(1L), eq("STOP_TASK"), eq(2L), eq(3),
                eq("task-stop:2:run-a:previous-command:gateway:17"));
    }

    @Test
    void repeatWhilePendingReturnsExistingCommandWithoutChangingState() {
        task.setActualStatus("STOPPING");
        NodeCommandDTO pending = new NodeCommandDTO();
        pending.setCommandId("previous-command");
        pending.setCommandType("STOP_TASK");
        pending.setStatus("RUNNING");
        when(commands.getCommandForNode("previous-command", 1L)).thenReturn(pending);
        assertThat(service.stopTask(2L)).isEqualTo("previous-command");
        verify(commands, never()).createCommand(anyString(), anyLong(), anyString(),
                anyLong(), anyInt(), anyString());
        verify(tasks, never()).updateRuntimeState(any());
    }

    @Test
    void repairsStoppingRowWhoseFormerCommandIdWasNeverPersisted() {
        task.setActualStatus("STOPPING");
        when(commands.getCommandForNode("previous-command", 1L))
                .thenThrow(exception(NODE_COMMAND_NOT_FOUND));
        assertThat(service.stopTask(2L)).isEqualTo("durable-command");
        assertThat(task.getLastCommandId()).isEqualTo("durable-command");
    }

    @Test
    void terminalCommandWithDelayedTaskStateCanBeRetried() {
        task.setActualStatus("STOPPING");
        NodeCommandDTO terminal = new NodeCommandDTO();
        terminal.setCommandType("STOP_TASK");
        terminal.setStatus("FAILED");
        when(commands.getCommandForNode("previous-command", 1L)).thenReturn(terminal);
        assertThat(service.stopTask(2L)).isEqualTo("durable-command");
        assertThat(task.getLastCommandId()).isEqualTo("durable-command");
    }
    @Test
    void runningHeartbeatCannotHidePendingStopOrItsFailure() {
        var runs=mock(com.linsight.module.aivideo.dal.mysql.task.TaskRunMapper.class);
        ReflectionTestUtils.setField(service,"taskRunMapper",runs);
        var run=new com.linsight.module.aivideo.dal.dataobject.task.TaskRunDO();run.setTaskId(2L);
        when(runs.selectByRunId("run-a")).thenReturn(run);
        var report=new com.linsight.module.aivideo.controller.node.task.vo.TaskRuntimeReportReqVO();
        report.setRunId("run-a");report.setConfigVersion(3);report.setStatus("RUNNING");
        report.setMetrics(java.util.Map.of("schemaVersion","1.0","gatewayRevision",5));
        task.setDesiredStatus("STOPPED");task.setActualStatus("STOPPING");
        service.reportRuntime(1L,report);
        assertThat(task.getActualStatus()).isEqualTo("STOPPING");
        task.setActualStatus("FAILED");task.setErrorCode("MODEL_COMMAND_FAILED");task.setErrorMessage("gateway configuration changed since command was queued");
        service.reportRuntime(1L,report);
        assertThat(task.getActualStatus()).isEqualTo("RUNNING");
        assertThat(task.getErrorCode()).isEqualTo("MODEL_COMMAND_FAILED");
        assertThat(task.getErrorMessage()).contains("gateway configuration changed");
    }
}
