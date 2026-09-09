package com.linsight.module.aivideo.controller.admin.model.vo;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import lombok.Data;

@Data
public class ModelDeployReqVO {
    @NotNull @Positive private Long modelVersionId;
    @NotNull @Positive private Long nodeId;
}
