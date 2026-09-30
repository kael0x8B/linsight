package com.linsight.module.aivideo.service.node;

import com.linsight.framework.common.exception.ServiceException;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeDeploymentPreflightRespVO;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeDeploymentConnectionReqVO;
import com.linsight.module.aivideo.integration.ssh.NodeDeploymentProperties;
import com.linsight.module.aivideo.integration.ssh.NodeSshClient;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertFalse;

class NodeDeploymentServiceImplTest {

    @Test
    void ubuntuWithSystemPython310CanUseManagedPythonDeployment() {
        NodeDeploymentServiceImpl service = new NodeDeploymentServiceImpl();
        org.springframework.test.util.ReflectionTestUtils.setField(service, "properties", new NodeDeploymentProperties());
        NodeSshClient.Connection connection = new NodeSshClient.Connection() {
            @Override public String execute(String command, String stdin) {
                return "ARCH=aarch64\nOS=Ubuntu 22.04.5 LTS\nOS_SUPPORTED=1\nPYTHON=3.10.12\n"
                        + "VENV=0\nFFMPEG=0\nSUDO=1\nRKNPU=1\nMEMORY_MB=7916\n"
                        + "MEMORY_AVAILABLE_MB=6971\nDISK_MB=50605\n";
            }
            @Override public void upload(byte[] content, String remotePath) {}
            @Override public String hostKey() { return "test-key"; }
            @Override public String hostKeyType() { return "ssh-ed25519"; }
            @Override public String hostKeyFingerprint() { return "SHA256:test"; }
            @Override public void close() {}
        };
        NodeDeploymentPreflightRespVO result = org.springframework.test.util.ReflectionTestUtils.invokeMethod(
                service, "inspect", connection, new NodeDeploymentConnectionReqVO());
        assertTrue(result.isSupported());
        assertFalse(result.isPythonSupported());
        assertTrue(result.getWarnings().stream().anyMatch(warning -> warning.contains("独立安装 Python 3.12.14")));
        assertTrue(result.getExecutionMode().contains("RKNN NPU"));
    }

    @Test
    void redeploymentMustKeepExistingNodeCodeForTheSameHost() {
        NodeDeploymentPreflightRespVO preflight = new NodeDeploymentPreflightRespVO();
        preflight.setExistingNodeCode("rk3566-field-001");

        assertDoesNotThrow(() -> NodeDeploymentServiceImpl.validateExistingNodeCode(
                preflight, "rk3566-field-001"));

        ServiceException error = assertThrows(ServiceException.class,
                () -> NodeDeploymentServiceImpl.validateExistingNodeCode(
                        preflight, "rk3566-field-01"));
        assertTrue(error.getMessage().contains("rk3566-field-001"));
    }

    @Test
    void aNewHostMayChooseANewNodeCode() {
        NodeDeploymentPreflightRespVO preflight = new NodeDeploymentPreflightRespVO();

        assertDoesNotThrow(() -> NodeDeploymentServiceImpl.validateExistingNodeCode(
                preflight, "rk3566-field-01"));
    }
}
