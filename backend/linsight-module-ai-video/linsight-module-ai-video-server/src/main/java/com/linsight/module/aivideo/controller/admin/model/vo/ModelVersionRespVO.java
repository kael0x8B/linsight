package com.linsight.module.aivideo.controller.admin.model.vo;

import lombok.Data;

import java.time.LocalDateTime;

@Data
public class ModelVersionRespVO {
    private Long id;
    private Long modelId;
    private String version;
    private String sourceRepository;
    private String sourceRevision;
    private String artifactName;
    private String artifactFormat;
    private String runtimeManifest;
    private Long artifactSize;
    private String sha256;
    private String licenseSpdx;
    private String validationStatus;
    private String publishStatus;
    private String executionStatus;
    private LocalDateTime executionReadyTime;
    private LocalDateTime publishedTime;
    private LocalDateTime createTime;
}
