package com.linsight.module.aivideo.service.node;
import com.linsight.framework.tenant.core.context.TenantContextHolder;
import com.linsight.module.aivideo.controller.admin.node.vo.*;
import com.linsight.module.aivideo.dal.mysql.node.*;
import com.linsight.module.aivideo.dal.dataobject.node.*;
import com.linsight.module.aivideo.integration.ssh.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.*;
import org.mockito.junit.jupiter.MockitoExtension;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
import static org.junit.jupiter.api.Assertions.*;
import java.util.function.Supplier;

@ExtendWith(MockitoExtension.class)
class NodeDeploymentFlowTest {
    @Mock NodeSshClient sshClient;
    @Mock NodeSshClient.Connection connection;
    @Mock NodeDeploymentMapper deploymentMapper;
    @Mock EdgeNodeMapper edgeNodeMapper;
    @Mock NodeDeploymentRunner deploymentRunner;
    @Mock NodeService nodeService;
    @Mock NodeOperationService operationService;
    @Spy NodeDeploymentProperties properties = new NodeDeploymentProperties();
    @InjectMocks NodeDeploymentServiceImpl service;
    static final String PROBE = "ARCH=aarch64\nOS=Ubuntu 24.04\nOS_SUPPORTED=1\nPYTHON=3.12.3\nSUDO=1\nFFMPEG=1\nMEMORY_MB=4096\nMEMORY_AVAILABLE_MB=2000\nDISK_MB=8192\n";

    @BeforeEach void setup() throws Exception {
        TenantContextHolder.setTenantId(7L); properties.setEnabled(true);
        lenient().when(sshClient.connect(any(), any())).thenReturn(connection);
        lenient().when(connection.execute(anyString(), nullable(String.class))).thenReturn(PROBE);
        lenient().when(connection.hostKeyFingerprint()).thenReturn("SHA256:test");
        lenient().when(operationService.exclusive(anyString(), any())).thenAnswer(i -> ((Supplier<?>)i.getArgument(1)).get());
        lenient().doAnswer(i -> { ((NodeDeploymentDO)i.getArgument(0)).setId(100L); return 1; }).when(deploymentMapper).insert(any(NodeDeploymentDO.class));
    }
    @AfterEach void clear() { TenantContextHolder.clear(); }
    NodeDeploymentCreateReqVO request() {
        var r = new NodeDeploymentCreateReqVO();
        r.setHost("edge.example"); r.setPort(22); r.setUsername("linaro"); r.setPassword("test-password");
        r.setNodeCode("edge-1"); r.setNodeName("Edge"); r.setRequestId("request-1");
        r.setControlPlaneUrl("http://control.example:48888"); r.setHostKeyType("ssh-ed25519");
        r.setHostKey("key"); r.setHostKeyFingerprint("SHA256:test"); return r;
    }
    @Test void initialDeploymentQueuesWithoutIssuingTokenBeforeExecutorStarts() {
        assertEquals(100L, service.createDeployment(request()));
        verifyNoInteractions(nodeService);
        verify(deploymentRunner).run(eq(100L), eq(7L), any(), isNull(), eq(false));
    }
    @Test void returnedRequestIdIsIdempotentAndDoesNotReconnect() {
        var previous = new NodeDeploymentDO(); previous.setId(99L); previous.setHost("edge.example"); previous.setNodeCode("edge-1");
        when(deploymentMapper.selectByRequestId("request-1")).thenReturn(previous);
        var request = request();
        assertEquals(99L, service.createDeployment(request));
        assertNull(request.getPassword());
        verifyNoInteractions(sshClient, deploymentRunner);
    }
    @Test void rejectedExecutorLeavesReadableFailedRecord() {
        doThrow(new org.springframework.core.task.TaskRejectedException("full")).when(deploymentRunner).run(anyLong(), anyLong(), any(), isNull(), anyBoolean());
        assertEquals(100L, service.createDeployment(request()));
        verify(deploymentRunner).submissionFailed(100L);
    }
    @Test void changedTargetIdentityPreventsMutation() throws Exception {
        when(connection.execute(anyString(), nullable(String.class))).thenReturn(PROBE + "NODE_ID=8\nTENANT_ID=7\nCREDENTIAL_DIGEST=digest\n");
        var request = request(); request.setNodeId(9L);
        assertThrows(RuntimeException.class, () -> service.createDeployment(request));
        verify(deploymentMapper, never()).insert(any(NodeDeploymentDO.class));
    }
    @Test void hostnameRedeployUsesCredentialIdentityNotIp() throws Exception {
        when(connection.execute(anyString(), nullable(String.class))).thenReturn(PROBE + "NODE_ID=8\nTENANT_ID=7\nCREDENTIAL_DIGEST=digest\n");
        var node = new EdgeNodeDO(); node.setId(8L); node.setCode("edge-1"); node.setStatus(0); node.setCredentialDigest("digest");
        when(edgeNodeMapper.selectById(8L)).thenReturn(node);
        var request = request(); request.setNodeId(8L);
        assertEquals(100L, service.createDeployment(request));
        verify(edgeNodeMapper, never()).selectByIpAddress(anyString());
        verify(deploymentRunner).run(eq(100L), eq(7L), any(), isNull(), eq(true));
    }
    @Test void memoryAvailabilityAndOsAreBlockingConditions() throws Exception {
        when(connection.execute(anyString(), nullable(String.class))).thenReturn(PROBE.replace("MEMORY_AVAILABLE_MB=2000", "MEMORY_AVAILABLE_MB=10"));
        assertFalse(service.preflight(request()).isSupported());
        when(connection.execute(anyString(), nullable(String.class))).thenReturn(PROBE.replace("OS_SUPPORTED=1", "OS_SUPPORTED=0"));
        assertFalse(service.preflight(request()).isSupported());
    }
    @Test void discoveredNpuDoesNotClaimAnInstalledExecutionBackend() throws Exception {
        when(connection.execute(anyString(), nullable(String.class))).thenReturn(PROBE + "RKNPU=1\n");
        var result = service.preflight(request());
        assertTrue(result.isRknpuAvailable());
        assertEquals("ONNX CPU / RKNN NPU（由部署模型决定）", result.getExecutionMode());
        assertTrue(result.getWarnings().stream().anyMatch(value -> value.contains("现有 ONNX 模型继续使用 CPU")));
    }
}
