package com.linsight.module.aivideo.controller.node.event.vo;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.Map;

@Data
public class EventIngestReqVO {
    @NotBlank @Size(max = 64) private String sourceEventId;
    @NotBlank @Size(max = 64) private String activityId;
    @NotBlank @Size(max = 255) private String dedupKey;
    @NotNull private Long taskId;
    @NotBlank @Size(max = 36) private String taskRunId;
    @NotNull private Long cameraId;
    @NotNull private Long algorithmId;
    @NotNull private Long pipelineVersionId;
    @NotNull private Long modelVersionId;
    @NotNull private Long ruleId;
    @NotNull private Long ruleVersionId;
    @NotBlank @Pattern(regexp = "^[A-Z][A-Z0-9_]{1,63}$") private String eventType;
    @NotBlank @Pattern(regexp = "INFO|MINOR|MAJOR|CRITICAL") private String severity;
    @NotNull private LocalDateTime occurredTime;
    @NotNull private LocalDateTime firstSeenTime;
    @NotNull private LocalDateTime lastSeenTime;
    @NotNull private Long durationMs;
    @DecimalMin("0") @DecimalMax("1") private BigDecimal maxConfidence;
    @Size(max = 128) private String trackId;
    @NotNull private Map<String, Object> objectSnapshot;
    @NotNull private Map<String, Object> taskSnapshot;
    @NotNull private Map<String, Object> pipelineSnapshot;
    @NotNull private Map<String, Object> modelSnapshot;
    @NotNull private Map<String, Object> ruleSnapshot;
}
