package com.linsight.module.aivideo.service.node;
import com.linsight.module.aivideo.dal.dataobject.node.NodeDeploymentDO;
import com.linsight.module.aivideo.dal.mysql.node.NodeDeploymentMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.*;
import org.mockito.junit.jupiter.MockitoExtension;
import static org.mockito.Mockito.*;
import static org.junit.jupiter.api.Assertions.*;

@ExtendWith(MockitoExtension.class)
class NodeDeploymentRecoveryTest {
    @Mock NodeDeploymentMapper deploymentMapper;
    @InjectMocks NodeDeploymentRunner runner;
    @Test void restartReconcilesOtherExecutorsWithoutStoredCredentials() {
        runner.reconcileInterrupted();
        verify(deploymentMapper).interruptOtherExecutors(runner.owner());
        assertNotNull(runner.owner());
    }
    @Test void rejectedQueueIsTerminalAndAuditable() {
        runner.submissionFailed(2L);
        var capture = ArgumentCaptor.forClass(NodeDeploymentDO.class);
        verify(deploymentMapper, times(2)).updateById(capture.capture());
        assertEquals("FAILED", capture.getAllValues().get(0).getStatus());
        assertEquals("REJECTED", capture.getAllValues().get(0).getStage());
        assertNotNull(capture.getAllValues().get(1).getFinishTime());
        verify(deploymentMapper).appendOutput(eq(2L), contains("REJECTED"));
    }
}
