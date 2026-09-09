package com.linsight.module.aivideo.controller.admin.task.vo;

import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import lombok.Data;

@Data
public class TaskRuleUpdateReqVO {
    @NotNull @Positive private Long id;
    @NotNull @Positive private Long ruleId;
    @NotNull @Positive private Long ruleVersionId;
    @NotNull @Positive private Integer expectedConfigVersion;
}
