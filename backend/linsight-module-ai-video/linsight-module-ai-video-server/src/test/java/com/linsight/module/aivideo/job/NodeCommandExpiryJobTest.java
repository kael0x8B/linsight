package com.linsight.module.aivideo.job;

import com.linsight.module.aivideo.service.model.ModelExecutionService;
import com.linsight.module.aivideo.service.node.NodeCommandDTO;
import com.linsight.module.aivideo.service.node.NodeCommandService;
import com.linsight.module.aivideo.service.node.NodeUpgradeService;
import com.linsight.module.aivideo.service.task.TaskService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;

import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class NodeCommandExpiryJobTest {

    @Mock private NodeCommandService nodeCommandService;
    @Mock private ModelExecutionService modelExecutionService;
    @Mock private TaskService taskService;
    @Mock private NodeUpgradeService nodeUpgradeService;
    @InjectMocks private NodeCommandExpiryJob job;

    @Test
    void expireMustPropagateTerminalReportToAllAggregateOwners() {
        NodeCommandDTO candidate = command(1L, 10L, "RUNNING");
        NodeCommandDTO expired = command(1L, 10L, "EXPIRED");
        when(nodeCommandService.getExpiredCommandsGlobal()).thenReturn(List.of(candidate));
        when(nodeCommandService.expireCommand(1L)).thenReturn(expired);

        job.expire();

        verify(modelExecutionService).applyCommandReport(expired);
        verify(taskService).applyCommandReport(expired);
        verify(nodeUpgradeService).applyCommandReport(expired);
    }

    @Test
    void expireMustNotReplayAggregateUpdatesWhenCompareAndSetLoses() {
        NodeCommandDTO candidate = command(1L, 10L, "RUNNING");
        when(nodeCommandService.getExpiredCommandsGlobal()).thenReturn(List.of(candidate));
        when(nodeCommandService.expireCommand(1L)).thenReturn(null);

        job.expire();

        verify(modelExecutionService, never()).applyCommandReport(candidate);
        verify(taskService, never()).applyCommandReport(candidate);
        verify(nodeUpgradeService, never()).applyCommandReport(candidate);
    }

    private static NodeCommandDTO command(Long id, Long tenantId, String status) {
        NodeCommandDTO command = new NodeCommandDTO();
        command.setId(id);
        command.setTenantId(tenantId);
        command.setCommandId("command-1");
        command.setStatus(status);
        return command;
    }
}
