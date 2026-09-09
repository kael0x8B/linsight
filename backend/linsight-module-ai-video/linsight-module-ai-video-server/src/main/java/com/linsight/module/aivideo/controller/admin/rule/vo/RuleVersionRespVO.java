package com.linsight.module.aivideo.controller.admin.rule.vo;

import lombok.Data;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;

@Data
public class RuleVersionRespVO {
    private Long id;
    private Long ruleId;
    private Integer version;
    private Map<String, Object> ast;
    private String naturalSummary;
    private String validationStatus;
    private List<String> validationErrors;
    private LocalDateTime publishedTime;
    private LocalDateTime createTime;
}
