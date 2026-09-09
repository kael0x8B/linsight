package com.linsight.module.aivideo.controller.admin.rule.vo;

import lombok.Data;

import java.time.LocalDateTime;

@Data
public class RuleRespVO {
    private Long id;
    private String name;
    private String code;
    private String description;
    private String eventType;
    private Long currentVersionId;
    private Integer status;
    private LocalDateTime createTime;
}
