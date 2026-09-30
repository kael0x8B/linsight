package com.linsight.module.aivideo.service.task;

import com.linsight.module.aivideo.dal.dataobject.task.TaskDO;
import com.linsight.module.aivideo.dal.mysql.task.TaskMapper;
import com.linsight.module.aivideo.service.algorithm.AlgorithmPackageService;
import com.linsight.module.aivideo.service.node.NodeService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class PackageTaskRemovalTest {
    @Mock TaskMapper taskMapper;
    @Mock AlgorithmPackageService algorithmPackageService;
    @Mock NodeService nodeService;
    @InjectMocks TaskServiceImpl service;

    private TaskDO stopped() {
        var task = new TaskDO(); task.setId(11L); task.setNodeId(5L); task.setPipelineVersionId(20L);
        task.setActualStatus("STOPPED"); task.setMetricsSnapshot("{\"gatewayRevision\":3}");
        when(taskMapper.selectById(11L)).thenReturn(task);
        return task;
    }
    @Test void removesDeviceReferenceBeforePlatformMetadata() {
        stopped(); service.deleteTask(11L);
        var order = inOrder(nodeService, taskMapper);
        order.verify(nodeService).removeGatewayTask(5L, 11L, 3);
        order.verify(taskMapper).deleteById(11L);
    }
    @Test void failureKeepsMetadataForRetry() {
        stopped(); doThrow(new IllegalStateException("offline")).when(nodeService).removeGatewayTask(5L, 11L, 3);
        assertThrows(IllegalStateException.class, () -> service.deleteTask(11L));
        verify(taskMapper, never()).deleteById(11L);
    }
}
