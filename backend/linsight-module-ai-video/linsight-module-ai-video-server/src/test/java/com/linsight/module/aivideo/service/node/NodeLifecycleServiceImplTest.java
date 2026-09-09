package com.linsight.module.aivideo.service.node;

import com.linsight.framework.common.exception.ServiceException;
import com.linsight.module.aivideo.dal.dataobject.node.EdgeNodeDO;
import com.linsight.module.aivideo.dal.mysql.node.EdgeNodeMapper;
import com.linsight.module.aivideo.dal.mysql.node.NodeCommandMapper;
import com.linsight.module.aivideo.service.task.TaskService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class NodeLifecycleServiceImplTest {
    @Mock private NodeOperationService operationService;
    @Mock private NodeUpgradeActivationService activationService;
    @org.junit.jupiter.api.BeforeEach
    void setupMutex() {
        org.mockito.Mockito.when(operationService.exclusive(org.mockito.ArgumentMatchers.anyString(), org.mockito.ArgumentMatchers.any()))
                .thenAnswer(invocation -> ((java.util.function.Supplier<?>) invocation.getArgument(1)).get());
    }
    @Mock private EdgeNodeMapper edgeNodeMapper;
    @Mock private NodeCommandMapper nodeCommandMapper;
    @Mock private NodeCommandService nodeCommandService;
    @Mock private TaskService taskService;
    @Mock private TransactionTemplate transactionTemplate;
    @InjectMocks private NodeLifecycleServiceImpl service;

    @Test
    void onlineNodeMustBeShutdownBeforeDeletion() {
        EdgeNodeDO node = node(1);
        when(edgeNodeMapper.selectById(20L)).thenReturn(node);

        ServiceException error = assertThrows(ServiceException.class,
                () -> service.deleteNode(20L));

        assertEquals(1_020_006_051, error.getCode());
        verify(edgeNodeMapper, never()).deleteById(20L);
    }

    @Test
    void referencedOfflineNodeMustNotBeDeleted() {
        EdgeNodeDO node = node(2);
        when(edgeNodeMapper.selectById(20L)).thenReturn(node);
        when(taskService.hasTasksForNode(20L)).thenReturn(true);

        ServiceException error = assertThrows(ServiceException.class,
                () -> service.deleteNode(20L));

        assertEquals(1_020_006_052, error.getCode());
        verify(edgeNodeMapper, never()).deleteById(20L);
    }

    @Test
    void unreferencedOfflineNodeCanBeDeleted() {
        EdgeNodeDO node = node(2);
        when(edgeNodeMapper.selectById(20L)).thenReturn(node);

        service.deleteNode(20L);

        verify(edgeNodeMapper).deleteById(20L);
    }

    @Test
    void activeCommandPreventsDeletionAndConflictingPowerActions() {
        when(edgeNodeMapper.selectById(20L)).thenReturn(node(2));
        org.mockito.Mockito.doThrow(new ServiceException(1_020_006_050, "active"))
                .when(operationService).requireIdle(org.mockito.ArgumentMatchers.eq(20L), org.mockito.ArgumentMatchers.isNull(), org.mockito.ArgumentMatchers.anyBoolean());
        assertThrows(ServiceException.class, () -> service.deleteNode(20L));
        assertThrows(ServiceException.class, () -> service.restartNode(20L));
        assertThrows(ServiceException.class, () -> service.shutdownNode(20L));
        verify(edgeNodeMapper, never()).deleteById(20L);
    }

    private static EdgeNodeDO node(int onlineStatus) {
        EdgeNodeDO node = new EdgeNodeDO();
        node.setId(20L);
        node.setStatus(0);
        node.setOnlineStatus(onlineStatus);
        return node;
    }
}
