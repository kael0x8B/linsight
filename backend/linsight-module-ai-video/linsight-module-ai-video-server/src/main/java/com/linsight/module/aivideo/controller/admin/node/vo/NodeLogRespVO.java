package com.linsight.module.aivideo.controller.admin.node.vo;

import lombok.Data;

import java.time.LocalDateTime;

@Data
public class NodeLogRespVO {
    private Long id;
    private Long nodeId;
    private Long taskId;
    private String runId;
    private String component;
    private String level;
    private String message;
    private String contextJson;
    private String diagnosticId;
    private LocalDateTime loggedAt;
}
