package com.linsight.module.aivideo.controller.admin.rule.vo;

import jakarta.validation.constraints.NotNull;
import lombok.Data;

import java.util.Map;

@Data
public class RuleVersionSaveReqVO {
    @NotNull private Long ruleId;
    @NotNull private Map<String, Object> ast;
}
