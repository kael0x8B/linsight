package com.linsight.module.aivideo.service.task;

import com.linsight.framework.common.exception.ServiceException;
import com.linsight.module.aivideo.controller.node.task.vo.TaskRemovalReportReqVO;
import com.linsight.module.aivideo.dal.dataobject.task.TaskDO;
import com.linsight.module.aivideo.dal.dataobject.task.TaskRunDO;
import com.linsight.module.aivideo.dal.mysql.task.TaskMapper;
import com.linsight.module.aivideo.dal.mysql.task.TaskRunMapper;
import com.linsight.module.aivideo.service.node.NodeCommandDTO;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.TransactionTemplate;

import java.util.function.Consumer;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class TaskRemovalSyncTest {
    private final TaskMapper tasks = mock(TaskMapper.class);
    private final TaskRunMapper runs = mock(TaskRunMapper.class);
    private final TaskServiceImpl service = new TaskServiceImpl();
    private final TaskDO task = new TaskDO();
    private final TaskRunDO run = new TaskRunDO();
    private final TaskRemovalReportReqVO report = new TaskRemovalReportReqVO();

    @BeforeEach void setUp() {
        ReflectionTestUtils.setField(service, "taskMapper", tasks);
        ReflectionTestUtils.setField(service, "taskRunMapper", runs);
        var transactions = mock(TransactionTemplate.class);
        ReflectionTestUtils.setField(service, "transactionTemplate", transactions);
        doAnswer(call -> {
            Consumer<TransactionStatus> callback = call.getArgument(0);
            callback.accept(mock(TransactionStatus.class));
            return null;
        }).when(transactions).executeWithoutResult(any());
        task.setId(31L); task.setNodeId(1L); task.setConfigVersion(2);
        task.setDesiredStatus("RUNNING"); task.setActualStatus("STOPPED");
        task.setMetricsSnapshot("{\"schemaVersion\":\"1.0\",\"gatewayRevision\":2}");
        run.setTaskId(31L); run.setConfigVersion(2); run.setRunId("known-run");
        report.setSchemaVersion("1.0"); report.setTaskId(31L); report.setConfigVersion(2);
        report.setRunId("known-run"); report.setGatewayRevision(3L);
        report.setRequestId("985c4bd7-ed6c-4f0c-bd99-62364a0f7e4b");
        report.setRemovedAt("2026-09-20T08:00:00Z");
        when(tasks.selectByIdForUpdate(31L)).thenReturn(task);
        when(runs.selectByRunId("known-run")).thenReturn(run);
    }

    @Test void removesKnownAssignmentAndRetainsHistoryDespiteOldDesiredRunning() {
        service.reportRemoval(1L, report);
        assertThat(task.getDesiredStatus()).isEqualTo("STOPPED");
        assertThat(task.getMetricsSnapshot()).contains("gatewayRemoved", report.getRequestId());
        verify(tasks).deleteById(task);
        verify(runs).updateById(run);
        verify(runs, never()).deleteById(anyLong());
        assertThat(run.getFinishTime()).isNotNull();
    }

    @Test void replayAfterCommitIsAcknowledgedWithoutAnotherMutation() {
        when(tasks.selectByIdForUpdate(31L)).thenReturn(null);
        service.reportRemoval(1L, report);
        verify(tasks, never()).deleteById(any(TaskDO.class));
        verifyNoInteractions(runs);
    }

    @Test void rejectsAnotherNode() {
        assertThatThrownBy(() -> service.reportRemoval(5L, report)).isInstanceOf(ServiceException.class);
        verify(tasks, never()).deleteById(any(TaskDO.class));
    }

    @Test void rejectsOldRevisionAndChangedConfiguration() {
        report.setGatewayRevision(2L);
        assertThatThrownBy(() -> service.reportRemoval(1L, report)).isInstanceOf(ServiceException.class);
        report.setGatewayRevision(3L); task.setConfigVersion(3);
        assertThatThrownBy(() -> service.reportRemoval(1L, report)).isInstanceOf(ServiceException.class);
        verify(tasks, never()).deleteById(any(TaskDO.class));
    }

    @Test void rejectsRunBelongingToAnotherTask() {
        run.setTaskId(32L);
        assertThatThrownBy(() -> service.reportRemoval(1L, report)).isInstanceOf(ServiceException.class);
        verify(tasks, never()).deleteById(any(TaskDO.class));
    }

    @Test void lateCommandReportCannotResurrectDeletedTaskOrBlockItsReceipt() {
        when(tasks.selectByIdForUpdate(31L)).thenReturn(null);
        var command = new NodeCommandDTO();
        command.setAggregateId(31L); command.setCommandType("START_TASK");
        service.applyCommandReport(command);
        verify(tasks, never()).updateRuntimeState(any());
    }

    @Test void nodeDeletePassesAuditActorToMybatisWithoutAdminLogin() {
        org.springframework.security.core.context.SecurityContextHolder.clearContext();
        task.setUpdater(null);
        service.reportRemoval(1L, report);
        var deleted = org.mockito.ArgumentCaptor.forClass(TaskDO.class);
        verify(tasks).deleteById(deleted.capture());
        assertThat(deleted.getValue().getUpdater()).isEqualTo("edge-agent");
        assertThat(deleted.getValue().getUpdateTime()).isNotNull();
        assertThat(run.getUpdater()).isEqualTo("edge-agent");
    }
}
