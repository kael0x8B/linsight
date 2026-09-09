package com.linsight.module.aivideo.service.node;

import com.linsight.module.aivideo.dal.dataobject.node.NodeCommandDO;
import com.linsight.module.aivideo.dal.mysql.node.NodeCommandMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.LocalDateTime;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class NodeCommandServiceImplTest {

    @Mock
    private NodeCommandMapper nodeCommandMapper;
    @Mock
    private NodeService nodeService;
    @InjectMocks
    private NodeCommandServiceImpl service;

    @Test
    void automaticCommandHasAuditActorWithoutAdminLogin() {
        service.createCommand("auto-entry", 20L, "ENTRY_FACE", 30L, 1, "entry-face:30");
        verify(nodeCommandMapper).insert(org.mockito.ArgumentMatchers.argThat((NodeCommandDO row) ->
                "system".equals(row.getCreator()) && "system".equals(row.getUpdater())));
    }

    @Test
    void createMustReturnOriginalCommandForSameIdempotencyKey() {
        NodeCommandDO existing = command("original-command", "QUEUED");
        when(nodeCommandMapper.selectByIdempotencyKey("deploy:10:20:1")).thenReturn(existing);

        String result = service.createCommand("replacement", 20L, "DEPLOY_MODEL", 30L, 1,
                "deploy:10:20:1");

        assertEquals("original-command", result);
        verify(nodeCommandMapper, never()).insert(any(NodeCommandDO.class));
    }

    @Test
    void duplicateTerminalReportMustRemainEnrichedForBusinessStateReplay() {
        NodeCommandDO existing = command("command-1", "SUCCEEDED");
        when(nodeCommandMapper.selectByCommandId("command-1")).thenReturn(existing);
        NodeCommandDTO report = new NodeCommandDTO();
        report.setCommandId("command-1");
        report.setStatus("SUCCEEDED");

        NodeCommandDTO result = service.reportCommand(20L, report);

        assertEquals("DEPLOY_MODEL", result.getCommandType());
        assertEquals(30L, result.getAggregateId());
        assertEquals("deploy:10:20:1", result.getIdempotencyKey());
        verify(nodeCommandMapper, never()).updateById(any(NodeCommandDO.class));
    }

    @Test
    void pullMustReturnNothingWhenAnotherPollerWinsCompareAndSet() {
        NodeCommandDO queued = command("command-1", "QUEUED");
        when(nodeCommandMapper.selectDispatchable(any(), any(), any())).thenReturn(List.of(queued));
        when(nodeCommandMapper.markSent(any(), any(), any(), any(), any())).thenReturn(0);

        assertNull(service.pullCommand(20L));
    }

    @Test
    void staleRunningCommandMustBeReclaimedWithUpdateTimeCompareAndSet() {
        NodeCommandDO running = command("command-1", "RUNNING");
        running.setSentTime(LocalDateTime.now().minusMinutes(10));
        running.setUpdateTime(LocalDateTime.now().minusMinutes(6));
        when(nodeCommandMapper.selectDispatchable(any(), any(), any())).thenReturn(List.of(running));
        when(nodeCommandMapper.markSent(
                eq(running.getId()), eq("RUNNING"), eq(running.getSentTime()),
                eq(running.getUpdateTime()), any()))
                .thenReturn(1);

        NodeCommandDTO result = service.pullCommand(20L);

        assertEquals("command-1", result.getCommandId());
        assertEquals("SENT", result.getStatus());
    }

    @Test
    void expiredRunningCommandMustBeClosedWithDiagnosticFailure() {
        NodeCommandDO running = command("command-expired", "RUNNING");
        running.setCommandType("START_TASK");
        running.setExpireTime(LocalDateTime.now().minusSeconds(1));
        when(nodeCommandMapper.selectById(running.getId())).thenReturn(running);
        when(nodeCommandMapper.markExpired(eq(running.getId()), eq("RUNNING"), any()))
                .thenReturn(1);

        NodeCommandDTO result = service.expireCommand(running.getId());

        assertNotNull(result);
        assertEquals("EXPIRED", result.getStatus());
        assertEquals("NODE_COMMAND_EXPIRED", result.getErrorCode());
        assertEquals("START_TASK", result.getCommandType());
    }

    private static NodeCommandDO command(String commandId, String status) {
        NodeCommandDO command = new NodeCommandDO();
        command.setId(1L);
        command.setCommandId(commandId);
        command.setNodeId(20L);
        command.setCommandType("DEPLOY_MODEL");
        command.setAggregateId(30L);
        command.setConfigVersion(1);
        command.setIdempotencyKey("deploy:10:20:1");
        command.setStatus(status);
        return command;
    }
}
