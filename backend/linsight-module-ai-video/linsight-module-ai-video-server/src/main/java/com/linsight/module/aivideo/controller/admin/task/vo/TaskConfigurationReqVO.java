package com.linsight.module.aivideo.controller.admin.task.vo;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.Data;
import java.util.Map;

/** Shared configuration; a task remains the camera-to-algorithm assignment. */
@Data
public class TaskConfigurationReqVO {
    @NotNull private Long algorithmId;
    private Long pipelineVersionId;
    private Long modelVersionId;
    @NotNull @Size(max = 20) private Map<@NotBlank String, @NotNull Long> modelBindings = Map.of();
    @NotNull private Long nodeId;
    private Long ruleId;
    private Long ruleVersionId;
    @NotNull private Map<String, Object> parameters;
}
