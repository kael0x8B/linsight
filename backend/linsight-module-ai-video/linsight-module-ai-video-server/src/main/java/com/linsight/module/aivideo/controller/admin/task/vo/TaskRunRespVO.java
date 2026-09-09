package com.linsight.module.aivideo.controller.admin.task.vo;

import lombok.Data;

import java.time.LocalDateTime;
import java.util.Map;

@Data
public class TaskRunRespVO {
    private Long id;
    private Long taskId;
    private String runId;
    private Integer configVersion;
    private String commandId;
    private String status;
    private LocalDateTime startTime;
    private LocalDateTime finishTime;
    private Map<String, Object> metricsSnapshot;
    private String diagnosticId;
    private String errorCode;
    private String errorMessage;
    private LocalDateTime createTime;
}
