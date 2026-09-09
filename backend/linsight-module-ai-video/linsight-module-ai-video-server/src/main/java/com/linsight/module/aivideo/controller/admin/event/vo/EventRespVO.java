package com.linsight.module.aivideo.controller.admin.event.vo;

import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

@Data
public class EventRespVO {
    private Long id;
    private String eventNo;
    private String sourceEventId;
    private Long taskId;
    private String taskRunId;
    private Long cameraId;
    private String cameraName;
    private String taskName;
    private Long nodeId;
    private Long algorithmId;
    private Long pipelineVersionId;
    private Long modelVersionId;
    private Long ruleId;
    private Long ruleVersionId;
    private String eventType;
    private String severity;
    private String status;
    private String evidenceStatus;
    private LocalDateTime occurredTime;
    private LocalDateTime firstSeenTime;
    private LocalDateTime lastSeenTime;
    private LocalDateTime closeTime;
    private Long durationMs;
    private BigDecimal maxConfidence;
    private String trackId;
    private Long assigneeId;
    private String handlingResult;
    private String falsePositiveReason;
    private Map<String, Object> objectSnapshot;
    private Map<String, Object> taskSnapshot;
    private Map<String, Object> pipelineSnapshot;
    private Map<String, Object> modelSnapshot;
    private Map<String, Object> ruleSnapshot;
    private List<EventMediaRespVO> media;
    private List<EventActionRespVO> actions;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;
}
