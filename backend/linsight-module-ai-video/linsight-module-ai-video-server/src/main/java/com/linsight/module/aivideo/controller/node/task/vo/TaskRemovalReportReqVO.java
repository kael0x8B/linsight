package com.linsight.module.aivideo.controller.node.task.vo;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
public class TaskRemovalReportReqVO {
    @NotBlank @Pattern(regexp = "1\\.0") private String schemaVersion;
    @NotNull @Positive private Long taskId;
    @NotNull @Positive private Long gatewayRevision;
    @NotNull @Positive private Integer configVersion;
    @NotBlank @Size(max = 36) private String runId;
    @NotBlank @Pattern(regexp = "[0-9a-fA-F-]{36}") private String requestId;
    @NotBlank @Size(max = 64) private String removedAt;
}
