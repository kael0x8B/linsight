package com.linsight.module.aivideo.controller.admin.node.vo;

import lombok.Data;

import java.util.List;

@Data
public class NodeDeploymentPreflightRespVO {
    private String hostKey;
    private String hostKeyType;
    private String hostKeyFingerprint;
    private String architecture;
    private String osSummary;
    private String pythonVersion;
    private boolean pythonSupported;
    private boolean venvAvailable;
    private boolean offlineDependenciesAvailable;
    private boolean ffmpegInstalled;
    private boolean sudoAvailable;
    private boolean rknpuAvailable;
    private long memoryMb;
    private long memoryAvailableMb;
    private String controlPlaneUrl;
    private String previousVersion;
    private String currentVersion;
    private boolean sourceRollbackAvailable;
    private Long remoteNodeId;
    private Long remoteTenantId;
    private long diskAvailableMb;
    private String executionMode;
    private boolean supported;
    private List<String> warnings;
    private Long existingNodeId;
    private String existingNodeCode;
    private String existingNodeName;
}
