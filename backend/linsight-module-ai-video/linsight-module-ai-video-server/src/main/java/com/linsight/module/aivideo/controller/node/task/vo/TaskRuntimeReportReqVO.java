package com.linsight.module.aivideo.controller.node.task.vo;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;

import java.util.Map;

@Data
public class TaskRuntimeReportReqVO {
    @NotBlank @Size(max = 36) private String runId;
    @NotNull private Integer configVersion;
    @NotBlank @Pattern(regexp = "RUNNING|FAILED|OFFLINE|STOPPED") private String status;
    @NotNull private Map<String, Object> metrics;
    @Size(max = 36) private String diagnosticId;
    @Size(max = 64) private String errorCode;
    @Size(max = 500) private String errorMessage;
}
