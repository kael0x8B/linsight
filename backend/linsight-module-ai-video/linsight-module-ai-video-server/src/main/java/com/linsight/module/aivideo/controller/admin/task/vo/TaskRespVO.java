package com.linsight.module.aivideo.controller.admin.task.vo;

import lombok.Data;

import java.time.LocalDateTime;
import java.util.Map;

@Data
public class TaskRespVO {
    private Long gatewayRevision;
    private Map<String, Object> gatewayConfiguration;
    private Long id;
    private String name;
    private String code;
    private Long cameraId;
    private Long algorithmId;
    private Long pipelineVersionId;
    private Long modelVersionId;
    private Map<String, Long> modelBindings;
    private Long nodeId;
    private Long ruleId;
    private Long ruleVersionId;
    private Map<String, Object> parameters;
    private String desiredStatus;
    private String actualStatus;
    private Integer configVersion;
    private String activeRunId;
    private String lastCommandId;
    private LocalDateTime lastHeartbeatTime;
    private Map<String, Object> metricsSnapshot;
    private String diagnosticId;
    private String errorCode;
    private String errorMessage;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;
}
