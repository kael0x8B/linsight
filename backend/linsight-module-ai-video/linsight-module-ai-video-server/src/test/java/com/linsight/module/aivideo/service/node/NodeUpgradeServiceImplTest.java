package com.linsight.module.aivideo.service.node;

import com.linsight.module.aivideo.controller.admin.node.vo.NodeUpgradeCreateReqVO;
import com.linsight.module.aivideo.dal.dataobject.node.NodeUpgradeDO;
import com.linsight.module.aivideo.dal.mysql.node.NodeUpgradeMapper;
import com.linsight.module.infra.api.file.FileApi;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.transaction.support.TransactionCallback;
import org.springframework.transaction.support.TransactionTemplate;

import java.nio.charset.StandardCharsets;
import java.io.ByteArrayOutputStream;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.zip.GZIPOutputStream;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class NodeUpgradeServiceImplTest {
    @Mock private NodeOperationService operationService;
    @Mock private com.linsight.module.aivideo.dal.mysql.node.EdgeNodeMapper edgeNodeMapper;
    @org.junit.jupiter.api.BeforeEach
    void setupNode() {
        var node = new com.linsight.module.aivideo.dal.dataobject.node.EdgeNodeDO();
        node.setAgentVersion("1.0.0");
        node.setResourceSnapshot("{\"activationGuard\":\"v1\",\"agentRollbackAvailable\":true}");
        org.mockito.Mockito.lenient().when(edgeNodeMapper.selectById(20L)).thenReturn(node);
    }

    @Mock private NodeUpgradeMapper nodeUpgradeMapper;
    @Mock private NodeService nodeService;
    @Mock private NodeCommandService nodeCommandService;
    @Mock private FileApi fileApi;
    @Mock private TransactionTemplate transactionTemplate;
    @InjectMocks private NodeUpgradeServiceImpl service;

    @Test
    void upgradeMustPersistDigestAndCreateDurableNodeCommand() throws Exception {
        byte[] content = gzip("signed-edge-release".getBytes(StandardCharsets.UTF_8));
        NodeUpgradeCreateReqVO request = new NodeUpgradeCreateReqVO();
        request.setNodeId(20L);
        request.setTargetVersion("1.1.0");
        request.setSignature("a".repeat(64));
        request.setFile(new MockMultipartFile(
                "file", "edge-agent.tar.gz", "application/gzip", content));
        when(fileApi.createFile(any(byte[].class), eq("edge-agent.tar.gz"),
                eq("ai-video/node-upgrade"), eq("application/gzip"))).thenReturn("file-ref");
        when(operationService.exclusive(any(), any())).thenAnswer(invocation -> ((java.util.function.Supplier<?>) invocation.getArgument(1)).get());

        service.createUpgrade(request);

        ArgumentCaptor<NodeUpgradeDO> upgrade = ArgumentCaptor.forClass(NodeUpgradeDO.class);
        verify(nodeUpgradeMapper).insert(upgrade.capture());
        assertEquals("UPGRADE", upgrade.getValue().getAction());
        assertEquals("1.1.0", upgrade.getValue().getTargetVersion());
        assertEquals(HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(content)),
                upgrade.getValue().getSha256());
        assertEquals("QUEUED", upgrade.getValue().getStatus());
        verify(nodeCommandService).createCommand(
                eq(upgrade.getValue().getCommandId()), eq(20L), eq("UPGRADE_AGENT"),
                any(), eq(1), eq("node-upgrade:20:1"));
    }

    @Test
    void activeUpgradeMustRejectAnotherRollback() {
        NodeUpgradeDO active = new NodeUpgradeDO();
        active.setStatus("RUNNING");
        when(nodeUpgradeMapper.selectLatestByNode(20L)).thenReturn(active);

        assertThrows(RuntimeException.class, () -> service.createRollback(20L));
    }

    @Test
    void offlineNodeHistoryMustUseExistenceValidationOnly() {
        service.getUpgradeList(20L);

        verify(nodeService).validateNodeExists(20L);
    }

    @Test
    void renamedNonGzipUpgradeMustBeRejectedBeforeStorage() {
        NodeUpgradeCreateReqVO request = new NodeUpgradeCreateReqVO();
        request.setNodeId(20L);
        request.setTargetVersion("1.1.0");
        request.setSignature("a".repeat(64));
        request.setFile(new MockMultipartFile(
                "file", "edge-agent.tar.gz", "application/gzip", "not-gzip".getBytes(StandardCharsets.UTF_8)));

        assertThrows(RuntimeException.class, () -> service.createUpgrade(request));

        org.mockito.Mockito.verify(fileApi, org.mockito.Mockito.never())
                .createFile(any(byte[].class), any(), any(), any());
    }

    private static byte[] gzip(byte[] content) throws Exception {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        try (GZIPOutputStream gzip = new GZIPOutputStream(output)) {
            gzip.write(content);
        }
        return output.toByteArray();
    }

    @Test
    void installSuccessWaitsForActivationAndDuplicateReportsCannotRegressIt() {
        NodeUpgradeDO upgrade = new NodeUpgradeDO();
        upgrade.setId(11L); upgrade.setAction("UPGRADE"); upgrade.setStatus("RUNNING"); upgrade.setTargetVersion("v2");
        when(nodeUpgradeMapper.selectByCommandId("cmd")).thenReturn(upgrade);
        NodeCommandDTO report = new NodeCommandDTO();
        report.setCommandId("cmd"); report.setCommandType("UPGRADE_AGENT"); report.setStatus("SUCCEEDED");
        report.setResult(java.util.Map.of("currentVersion", "v2", "restartRequired", true));
        service.applyCommandReport(report);
        assertEquals("AWAITING_ACTIVATION", upgrade.getStatus());
        org.junit.jupiter.api.Assertions.assertNull(upgrade.getFinishTime());
        upgrade.setStatus("SUCCEEDED");
        report.setStatus("RUNNING");
        service.applyCommandReport(report);
        assertEquals("SUCCEEDED", upgrade.getStatus());
        verify(nodeUpgradeMapper, org.mockito.Mockito.times(1)).update(eq(upgrade), any());
    }

    @Test
    void unexpectedReportedVersionCannotReplaceRequestedVersion() {
        NodeUpgradeDO upgrade = new NodeUpgradeDO();
        upgrade.setId(11L); upgrade.setAction("UPGRADE"); upgrade.setStatus("RUNNING"); upgrade.setTargetVersion("v2");
        when(nodeUpgradeMapper.selectByCommandId("cmd")).thenReturn(upgrade);
        NodeCommandDTO report = new NodeCommandDTO();
        report.setCommandId("cmd"); report.setCommandType("UPGRADE_AGENT"); report.setStatus("SUCCEEDED");
        report.setResult(java.util.Map.of("currentVersion", "v1"));
        service.applyCommandReport(report);
        assertEquals("FAILED", upgrade.getStatus());
        assertEquals("v2", upgrade.getTargetVersion());
    }
}
