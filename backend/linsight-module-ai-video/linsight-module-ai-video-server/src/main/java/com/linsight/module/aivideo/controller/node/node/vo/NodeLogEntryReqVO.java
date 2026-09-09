package com.linsight.module.aivideo.controller.node.node.vo;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
public class NodeLogEntryReqVO {
    @NotBlank
    @Size(max = 36)
    private String entryId;
    private Long taskId;
    @Size(max = 36)
    private String runId;
    @NotBlank
    @Size(max = 32)
    @Pattern(regexp = "[A-Z0-9_.-]+")
    private String component;
    @NotBlank
    @Pattern(regexp = "DEBUG|INFO|WARN|ERROR")
    private String level;
    @NotBlank
    @Size(max = 2000)
    private String message;
    @Size(max = 4000)
    private String contextJson;
    @Size(max = 36)
    private String diagnosticId;
    @NotNull
    private Long timestampMillis;
}
