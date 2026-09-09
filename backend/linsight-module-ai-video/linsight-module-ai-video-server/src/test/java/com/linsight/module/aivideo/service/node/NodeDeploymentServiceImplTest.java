package com.linsight.module.aivideo.service.node;

import com.linsight.framework.common.exception.ServiceException;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeDeploymentPreflightRespVO;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class NodeDeploymentServiceImplTest {

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
