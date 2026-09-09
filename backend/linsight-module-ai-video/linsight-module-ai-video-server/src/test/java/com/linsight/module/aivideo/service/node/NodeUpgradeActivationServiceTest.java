package com.linsight.module.aivideo.service.node;
import com.linsight.module.aivideo.dal.dataobject.node.*;
import com.linsight.module.aivideo.dal.mysql.node.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.*;
import org.mockito.junit.jupiter.MockitoExtension;
import java.time.LocalDateTime;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
import static org.junit.jupiter.api.Assertions.*;

@ExtendWith(MockitoExtension.class)
class NodeUpgradeActivationServiceTest {
    @Mock NodeUpgradeMapper upgradeMapper;
    @Mock EdgeNodeMapper nodeMapper;
    @Mock NodeCommandMapper commandMapper;
    @InjectMocks NodeUpgradeActivationService service;
    NodeUpgradeDO upgrade;
    EdgeNodeDO node;
    @BeforeEach void setup() {
        upgrade = new NodeUpgradeDO(); upgrade.setId(1L); upgrade.setNodeId(2L);
        upgrade.setStatus("AWAITING_ACTIVATION"); upgrade.setTargetVersion("v2"); upgrade.setPreviousVersion("v1");
        upgrade.setActivationRequestedAt(LocalDateTime.now().minusSeconds(30));
        when(upgradeMapper.selectLatestByNode(2L)).thenReturn(upgrade);
        node = new EdgeNodeDO(); node.setOnlineStatus(1); node.setAgentVersion("v2");
        node.setLastHeartbeatTime(LocalDateTime.now()); node.setResourceSnapshot("{\"runtimeStatus\":\"UP\"}");
        lenient().when(nodeMapper.selectById(2L)).thenReturn(node);
    }
    @Test void freshHealthyTargetConfirmsSuccess() {
        service.heartbeatReceived(2L);
        assertEquals("SUCCEEDED", upgrade.getStatus());
        verify(upgradeMapper).update(eq(upgrade), any());
    }
    @Test void staleHeartbeatAndWrongVersionDoNotConfirm() {
        node.setLastHeartbeatTime(upgrade.getActivationRequestedAt().minusSeconds(1));
        service.heartbeatReceived(2L);
        node.setLastHeartbeatTime(LocalDateTime.now()); node.setAgentVersion("v1");
        service.heartbeatReceived(2L);
        verify(upgradeMapper, never()).update(any(), any());
    }
    @Test void unhealthyRuntimeDoesNotConfirm() {
        node.setResourceSnapshot("{\"runtimeStatus\":\"DOWN\"}");
        service.heartbeatReceived(2L);
        assertEquals("AWAITING_ACTIVATION", upgrade.getStatus());
    }
    @Test void activationTimeoutMarksPriorVersionWithoutFalseSuccess() {
        upgrade.setStatus("VERIFYING"); upgrade.setActivationRequestedAt(LocalDateTime.now().minusMinutes(6));
        node.setAgentVersion("v1");
        service.heartbeatReceived(2L);
        assertEquals("FAILED", upgrade.getStatus());
        assertEquals("PREVIOUS_VERSION_ACTIVE", upgrade.getStage());
    }
    @Test void externalRestartFailureClosesWaitingActivation() {
        node.setAgentVersion("v1");
        node.setResourceSnapshot("{\"runtimeStatus\":\"UP\",\"failedAgentVersion\":\"v2\"}");
        service.heartbeatReceived(2L);
        assertEquals("FAILED", upgrade.getStatus());
        assertEquals("AUTO_RESTORED", upgrade.getStage());
    }
}
