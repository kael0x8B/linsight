package com.linsight.module.aivideo.controller.admin.algorithm.vo;

import lombok.Data;

import java.time.LocalDateTime;
import java.util.Map;

@Data
public class AlgorithmRespVO {
    private Long id;
    private String name;
    private String code;
    private String category;
    private String sceneGroup;
    private String implementationType;
    private String description;
    private String capabilityKey;
    private java.util.List<String> requiredCapabilities;
    private String eventType;
    private Long defaultModelId;
    private Long currentPipelineVersionId;
    private String pipelineAcceptanceStatus;
    private Map<String, Object> parameterSchema;
    private Map<String, Object> defaultParameters;
    private Integer status;
    private LocalDateTime createTime;
}
