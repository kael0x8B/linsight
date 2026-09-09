package com.linsight.module.aivideo.controller.admin.model.vo;

import lombok.Data;

import java.time.LocalDateTime;
import java.util.List;

@Data
public class ModelRespVO {
    private Long id;
    private String name;
    private String code;
    private String sourceType;
    private String description;
    private Long currentVersionId;
    private Long latestVersionId;
    private String latestVersion;
    private String artifactFormat;
    private Long artifactSize;
    private String licenseSpdx;
    private String validationStatus;
    private String publishStatus;
    /** Output labels declared by the displayed version; independent of algorithm adoption. */
    private List<String> outputLabels = List.of();
    private Integer versionCount;
    private Integer deployedNodeCount;
    private Integer readyNodeCount;
    private List<ModelCapabilityRespVO> capabilities;
    private Integer status;
    private LocalDateTime createTime;
}
