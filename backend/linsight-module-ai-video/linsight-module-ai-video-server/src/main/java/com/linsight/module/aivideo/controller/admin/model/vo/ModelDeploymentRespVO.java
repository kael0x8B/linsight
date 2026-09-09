package com.linsight.module.aivideo.controller.admin.model.vo;

import lombok.Data;
import java.time.LocalDateTime;

@Data
public class ModelDeploymentRespVO {
    private String modelName;
    private String modelVersion;
    private Long id;
    private Long modelVersionId;
    private Long nodeId;
    private Integer configVersion;
    private String desiredStatus;
    private String actualStatus;
    private String commandId;
    private String diagnosticId;
    private String backend;
    private String device;
    private String errorCode;
    private String errorMessage;
    private LocalDateTime readyTime;
    private LocalDateTime createTime;
}
