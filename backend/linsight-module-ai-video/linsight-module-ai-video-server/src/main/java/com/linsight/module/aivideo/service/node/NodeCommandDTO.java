package com.linsight.module.aivideo.service.node;

import lombok.Data;

import java.util.Map;

@Data
public class NodeCommandDTO {
    private java.time.LocalDateTime createTime;
    private java.time.LocalDateTime finishTime;
    private String resultSummary;
    private Long id;
    private Long tenantId;
    private String commandId;
    private Long nodeId;
    private String commandType;
    private Long aggregateId;
    private Integer configVersion;
    private String idempotencyKey;
    private String status;
    private String stage;
    private String diagnosticId;
    private String backend;
    private String device;
    private Integer preprocessMillis;
    private Integer inferenceMillis;
    private Integer postprocessMillis;
    private Map<String, Object> result;
    private String errorCode;
    private String errorMessage;
}
