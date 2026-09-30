package com.linsight.module.aivideo.service.node;

import com.linsight.framework.common.exception.ServiceException;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeBootstrapTokenRespVO;
import com.linsight.module.aivideo.controller.node.node.vo.NodeHeartbeatReqVO;
import com.linsight.module.aivideo.controller.node.node.vo.NodeHeartbeatRespVO;
import com.linsight.module.aivideo.controller.node.node.vo.NodeRegisterReqVO;
import com.linsight.module.aivideo.controller.node.node.vo.NodeRegistrationRespVO;
import com.linsight.module.aivideo.dal.dataobject.node.EdgeNodeDO;
import com.linsight.module.aivideo.dal.dataobject.node.NodeBootstrapTokenDO;
import com.linsight.module.aivideo.dal.mysql.node.EdgeNodeMapper;
import com.linsight.module.aivideo.dal.mysql.node.NodeBootstrapTokenMapper;
import com.linsight.module.aivideo.enums.node.NodeOnlineStatusEnum;
import com.linsight.module.aivideo.integration.runtime.NodePreviewTunnelHandler;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.LocalDateTime;
import java.util.HexFormat;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class NodeServiceImplTest {
    @Mock private NodeUpgradeActivationService activationService;
    @Mock private NodePreviewTunnelHandler gatewayTunnel;

    @Mock
    private NodeBootstrapTokenMapper nodeBootstrapTokenMapper;
    @Mock
    private EdgeNodeMapper edgeNodeMapper;
    @InjectMocks
    private NodeServiceImpl nodeService;

    @Test
    void taskCapacityPreflightIsNodeScopedReadOnlyAndKeepsConflictDetails() {
        EdgeNodeDO node = new EdgeNodeDO();
        node.setStatus(0);
        node.setOnlineStatus(NodeOnlineStatusEnum.ONLINE.getStatus());
        when(edgeNodeMapper.selectById(100L)).thenReturn(node);
        Map<String, Object> report = Map.of(
                "allowed", false,
                "code", "MODEL_CAPACITY_EXCEEDED",
                "message", "需要 5/4 个槽位；任务 8 使用模型 122");
        when(gatewayTunnel.request(eq(100L), nullable(Long.class), eq("gateway.rpc"), anyMap()))
                .thenReturn(new NodePreviewTunnelHandler.TunnelResult(
                        Map.of("ok", true, "data", report), null, null));

        var result = nodeService.preflightTaskCapacity(100L, 9L, java.util.List.of(122L, 123L, 122L));

        assertFalse(result.allowed());
        assertEquals("MODEL_CAPACITY_EXCEEDED", result.code());
        assertTrue(result.message().contains("任务 8"));
        verify(gatewayTunnel).request(eq(100L), nullable(Long.class), eq("gateway.rpc"),
                eq(Map.of("action", "task.capacity.preflight", "payload",
                        Map.of("taskId", 9L, "modelVersionIds", java.util.List.of(122L, 123L)))));
        verify(edgeNodeMapper, never()).updateById(any(EdgeNodeDO.class));
    }

    @Test
    void createBootstrapTokenMustPersistOnlyDigest() {
        NodeBootstrapTokenRespVO result = nodeService.createBootstrapToken("一号节点", 30);

        ArgumentCaptor<NodeBootstrapTokenDO> captor = ArgumentCaptor.forClass(NodeBootstrapTokenDO.class);
        verify(nodeBootstrapTokenMapper).insert(captor.capture());
        assertNotNull(result.getToken());
        assertNotEquals(result.getToken(), captor.getValue().getTokenDigest());
        assertEquals(64, captor.getValue().getTokenDigest().length());
        assertTrue(result.getExpireTime().isAfter(LocalDateTime.now().plusMinutes(29)));
    }

    @Test
    void registerMustConsumeTokenOnceAndReturnCredentialOnce() {
        NodeBootstrapTokenDO token = bootstrapToken("bootstrap-secret");
        when(nodeBootstrapTokenMapper.selectByTokenDigest(sha256("bootstrap-secret"))).thenReturn(token);
        when(nodeBootstrapTokenMapper.markUsedIfAvailable(eq(7L), any(LocalDateTime.class))).thenReturn(1);
        when(edgeNodeMapper.selectByTenantIdAndCode(9L, "EDGE-001")).thenReturn(null);
        doAnswer(invocation -> {
            invocation.<EdgeNodeDO>getArgument(0).setId(100L);
            return 1;
        }).when(edgeNodeMapper).insert(any(EdgeNodeDO.class));

        NodeRegistrationRespVO result = nodeService.registerNode(registerReqVO("bootstrap-secret"), "192.0.2.20");

        assertEquals(100L, result.getNodeId());
        assertEquals(9L, result.getTenantId());
        assertNotNull(result.getCredential());
        ArgumentCaptor<EdgeNodeDO> captor = ArgumentCaptor.forClass(EdgeNodeDO.class);
        verify(edgeNodeMapper).insert(captor.capture());
        assertEquals(9L, captor.getValue().getTenantId());
        assertNotEquals(result.getCredential(), captor.getValue().getCredentialDigest());
        assertEquals(sha256(result.getCredential()), captor.getValue().getCredentialDigest());
    }

    @Test
    void registerMustRejectAlreadyConsumedToken() {
        NodeBootstrapTokenDO token = bootstrapToken("used-token");
        token.setUsedTime(LocalDateTime.now().minusMinutes(1));
        when(nodeBootstrapTokenMapper.selectByTokenDigest(sha256("used-token"))).thenReturn(token);

        ServiceException exception = assertThrows(ServiceException.class,
                () -> nodeService.registerNode(registerReqVO("used-token"), "192.0.2.20"));

        assertEquals(1_020_006_000, exception.getCode());
        verify(edgeNodeMapper, never()).insert(any(EdgeNodeDO.class));
    }

    @Test
    void authenticateMustBindCredentialToNodeAndTenant() {
        EdgeNodeDO node = new EdgeNodeDO();
        node.setId(100L);
        node.setTenantId(9L);
        node.setStatus(0);
        node.setCredentialDigest(sha256("node-secret"));
        when(edgeNodeMapper.selectForAuthentication(100L)).thenReturn(node);

        assertTrue(nodeService.authenticateNode(100L, 9L, "node-secret"));
        assertFalse(nodeService.authenticateNode(100L, 8L, "node-secret"));
        assertFalse(nodeService.authenticateNode(100L, 9L, "wrong-secret"));
    }

    @Test
    void heartbeatMustRejectOlderSequence() {
        when(edgeNodeMapper.updateHeartbeatIfNotOlder(any(EdgeNodeDO.class), eq(3L))).thenReturn(0);

        ServiceException exception = assertThrows(ServiceException.class,
                () -> nodeService.reportHeartbeat(100L, heartbeatReqVO(3L)));

        assertEquals(1_020_006_004, exception.getCode());
    }

    @Test
    void heartbeatMustAcceptSameSequenceAsIdempotentPowerLossRetry() {
        when(edgeNodeMapper.updateHeartbeatIfNotOlder(any(EdgeNodeDO.class), eq(3L))).thenReturn(1);

        NodeHeartbeatRespVO result = nodeService.reportHeartbeat(100L, heartbeatReqVO(3L));

        assertEquals(3L, result.getAcceptedSequence());
        verify(edgeNodeMapper).updateHeartbeatIfNotOlder(any(EdgeNodeDO.class), eq(3L));
    }

    @Test
    void heartbeatMustPersistResourceSnapshotWithoutCredentials() {
        when(edgeNodeMapper.updateHeartbeatIfNotOlder(any(EdgeNodeDO.class), eq(4L))).thenReturn(1);

        NodeHeartbeatRespVO result = nodeService.reportHeartbeat(100L, heartbeatReqVO(4L));

        ArgumentCaptor<EdgeNodeDO> captor = ArgumentCaptor.forClass(EdgeNodeDO.class);
        verify(edgeNodeMapper).updateHeartbeatIfNotOlder(captor.capture(), eq(4L));
        assertEquals(4L, result.getAcceptedSequence());
        assertEquals(1, captor.getValue().getOnlineStatus());
        assertTrue(captor.getValue().getResourceSnapshot().contains("\"cpuUsage\":25.5"));
        assertTrue(captor.getValue().getResourceSnapshot().contains("\"npuUsage\":37.5"));
        assertTrue(captor.getValue().getResourceSnapshot().contains("\"diskCleanupStatus\":\"RECLAIMED\""));
        assertTrue(captor.getValue().getResourceSnapshot().contains("\"diskCleanupFreedBytes\":1024"));
        assertFalse(captor.getValue().getResourceSnapshot().contains("credential"));
    }

    @Test
    void expiredHeartbeatMustMarkNodeOfflineWithAuditUpdater() {
        EdgeNodeDO node = new EdgeNodeDO();
        node.setId(100L);
        node.setOnlineStatus(1);
        node.setLastHeartbeatTime(LocalDateTime.now().minusMinutes(2));
        when(edgeNodeMapper.selectById(100L)).thenReturn(node);

        nodeService.markOfflineIfHeartbeatExpired(100L, LocalDateTime.now().minusSeconds(30));

        verify(edgeNodeMapper).updateById(argThat((EdgeNodeDO update) ->
                NodeOnlineStatusEnum.OFFLINE.getStatus().equals(update.getOnlineStatus())
                        && "node-offline-detector".equals(update.getUpdater())));
    }

    private static NodeBootstrapTokenDO bootstrapToken(String plaintext) {
        NodeBootstrapTokenDO token = new NodeBootstrapTokenDO();
        token.setId(7L);
        token.setTenantId(9L);
        token.setTokenDigest(sha256(plaintext));
        token.setExpireTime(LocalDateTime.now().plusMinutes(10));
        return token;
    }

    private static NodeRegisterReqVO registerReqVO(String bootstrapToken) {
        NodeRegisterReqVO reqVO = new NodeRegisterReqVO();
        reqVO.setBootstrapToken(bootstrapToken);
        reqVO.setCode("EDGE-001");
        reqVO.setName("一号节点");
        reqVO.setAgentVersion("0.1.0");
        reqVO.setHostName("edge-01");
        return reqVO;
    }

    private static NodeHeartbeatReqVO heartbeatReqVO(Long sequence) {
        NodeHeartbeatReqVO reqVO = new NodeHeartbeatReqVO();
        reqVO.setSequence(sequence);
        reqVO.setAgentTime(LocalDateTime.now().minusSeconds(1));
        reqVO.setAgentVersion("0.1.0");
        reqVO.setHostName("edge-01");
        reqVO.setIpAddress("192.0.2.20");
        reqVO.setCpuUsage(25.5);
        reqVO.setMemoryUsedBytes(1024L);
        reqVO.setMemoryTotalBytes(4096L);
        reqVO.setDiskUsedBytes(2048L);
        reqVO.setDiskTotalBytes(8192L);
        reqVO.setNpuUsage(37.5);
        reqVO.setDiskCleanupStatus("RECLAIMED");
        reqVO.setDiskCleanupLastRunEpochSeconds(1_789_084_800L);
        reqVO.setDiskCleanupBeforePercent(86);
        reqVO.setDiskCleanupAfterPercent(72);
        reqVO.setDiskCleanupFreedBytes(1024L);
        reqVO.setDiskCleanupActions("pip_cache,old_snapshot,journal");
        return reqVO;
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception exception) {
            throw new IllegalStateException(exception);
        }
    }

}
