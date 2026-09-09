package com.linsight.module.aivideo.controller.admin.node.vo;

import lombok.Data;

import java.time.LocalDateTime;

@Data
public class NodeDiagnosticRespVO {
    private Long id;
    private Long nodeId;
    private Long taskId;
    private LocalDateTime rangeStart;
    private LocalDateTime rangeEnd;
    private String status;
    private String fileName;
    private Integer logCount;
    private LocalDateTime expiresAt;
    private String errorMessage;
    private String accessUrl;
    private LocalDateTime createTime;
}
