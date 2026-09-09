package com.linsight.module.aivideo.service.node;
import com.linsight.framework.common.exception.ServiceException;
import com.linsight.framework.tenant.core.context.TenantContextHolder;
import com.linsight.module.aivideo.dal.mysql.node.*;
import com.linsight.module.aivideo.dal.dataobject.node.NodeUpgradeDO;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.*;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.transaction.support.TransactionCallback;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
import static org.junit.jupiter.api.Assertions.*;

@ExtendWith(MockitoExtension.class)
class NodeOperationServiceTest {
    @Mock NodeOperationMutexMapper mutexMapper;
    @Mock NodeDeploymentMapper deploymentMapper;
    @Mock NodeCommandMapper commandMapper;
    @Mock NodeUpgradeMapper upgradeMapper;
    @Mock EdgeNodeMapper edgeNodeMapper;
    @Mock TransactionTemplate transactionTemplate;
    @InjectMocks NodeOperationService service;
    @AfterEach void clearTenant() { TenantContextHolder.clear(); }

    @Test void lockIsTenantScopedAndHeldBeforeMutation() {
        TenantContextHolder.setTenantId(7L);
        when(transactionTemplate.execute(any())).thenAnswer(i -> ((TransactionCallback<?>) i.getArgument(0)).doInTransaction(null));
        String result = service.exclusive("node:2", () -> {
            var order = inOrder(mutexMapper);
            order.verify(mutexMapper).ensure(7L, "node:2");
            order.verify(mutexMapper).lock(7L, "node:2");
            return "reserved";
        });
        assertEquals("reserved", result);
    }

    @Test void activeDeploymentBlocksAllCommandTypes() {
        when(deploymentMapper.hasActive(2L, "host")).thenReturn(true);
        assertThrows(ServiceException.class, () -> service.requireIdle(2L, "host", false));
        assertThrows(ServiceException.class, () -> service.requireIdle(2L, "host", true));
        verifyNoInteractions(commandMapper, upgradeMapper);
    }

    @Test void onlyActivationRestartMayPassWaitingUpgrade() {
        NodeUpgradeDO upgrade = new NodeUpgradeDO(); upgrade.setStatus("AWAITING_ACTIVATION");
        when(upgradeMapper.selectLatestByNode(2L)).thenReturn(upgrade);
        assertThrows(ServiceException.class, () -> service.requireIdle(2L, null, false));
        assertDoesNotThrow(() -> service.requireIdle(2L, null, true));
        upgrade.setStatus("VERIFYING");
        assertThrows(ServiceException.class, () -> service.requireIdle(2L, null, true));
    }
}
