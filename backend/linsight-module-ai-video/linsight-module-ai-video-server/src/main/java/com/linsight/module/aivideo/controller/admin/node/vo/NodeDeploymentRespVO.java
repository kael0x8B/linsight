package com.linsight.module.aivideo.controller.admin.node.vo;

import lombok.Data;

import java.time.LocalDateTime;

@Data
public class NodeDeploymentRespVO {
    private Long id;
    private String logStatus;
    private Boolean logTruncated;
    private String controlPlaneUrl;
    private String previousVersion;
    private String targetVersion;
    private String host;
    private Integer port;
    private String username;
    private String nodeCode;
    private String nodeName;
    private String operationType;
    private String targetArch;
    private String osSummary;
    private String pythonVersion;
    private String runtimePackageSha256;
    private String status;
    private String stage;
    private Integer progress;
    private String message;
    private String outputLog;
    private String diagnosticId;
    private Long edgeNodeId;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;
    private LocalDateTime finishTime;
}
