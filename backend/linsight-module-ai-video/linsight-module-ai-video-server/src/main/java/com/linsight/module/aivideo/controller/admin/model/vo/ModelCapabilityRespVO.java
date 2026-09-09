package com.linsight.module.aivideo.controller.admin.model.vo;

import lombok.Data;

@Data
public class ModelCapabilityRespVO {
    private Long algorithmId;
    private String name;
    private String code;
    private String capabilityKey;
    private String sceneGroup;
    private String acceptanceStatus;
}
