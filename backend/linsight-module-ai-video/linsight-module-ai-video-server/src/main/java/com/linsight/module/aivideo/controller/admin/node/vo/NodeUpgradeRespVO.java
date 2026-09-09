package com.linsight.module.aivideo.controller.admin.node.vo;

import lombok.Data;

import java.time.LocalDateTime;

@Data
public class NodeUpgradeRespVO {
    private Long id;
    private Long nodeId;
    private String action;
    private String targetVersion;
    private String previousVersion;
    private LocalDateTime activationRequestedAt;
    private String packageName;
    private String sha256;
    private String commandId;
    private Integer configVersion;
    private String status;
    private String stage;
    private String diagnosticId;
    private String resultSummary;
    private String errorCode;
    private String errorMessage;
    private LocalDateTime finishTime;
    private LocalDateTime createTime;
}
