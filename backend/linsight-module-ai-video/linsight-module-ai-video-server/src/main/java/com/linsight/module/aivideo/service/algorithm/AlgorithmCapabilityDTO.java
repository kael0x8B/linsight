package com.linsight.module.aivideo.service.algorithm;

import lombok.AllArgsConstructor;
import lombok.Data;

@Data
@AllArgsConstructor
public class AlgorithmCapabilityDTO {
    private Long algorithmId;
    private Long modelId;
    private String name;
    private String code;
    private String capabilityKey;
    private String sceneGroup;
    private String acceptanceStatus;
}
