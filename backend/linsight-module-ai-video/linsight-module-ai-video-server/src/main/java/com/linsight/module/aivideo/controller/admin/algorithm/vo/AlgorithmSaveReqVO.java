package com.linsight.module.aivideo.controller.admin.algorithm.vo;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;

import java.util.List;
import java.util.Map;

@Data
public class AlgorithmSaveReqVO {
    private Long id;
    @NotBlank @Size(max = 100)
    private String name;
    @NotBlank @Pattern(regexp = "^[a-z][a-z0-9-]{1,63}$")
    private String code;
    @NotBlank @Pattern(regexp = "CORE|EXTENSION|CUSTOM")
    private String category;
    @NotBlank @Pattern(regexp = "^[A-Z][A-Z0-9_]{1,63}$")
    private String sceneGroup = "GENERAL";
    @NotBlank @Pattern(regexp = "MODEL_DIRECT|MODEL_FILTER|TRACK_RULE|CLASSICAL_CV|COMPOSITE")
    private String implementationType = "MODEL_DIRECT";
    @Size(max = 500)
    private String description;
    @NotBlank @Pattern(regexp = "^[a-z][a-z0-9.-]{1,63}$")
    private String capabilityKey;
    @NotNull @Size(max = 20)
    private List<@Pattern(regexp = "^[a-z][a-z0-9.-]{1,63}$") String> requiredCapabilities = List.of();
    @Size(max = 64)
    private String eventType;
    private Long defaultModelId;
    @NotNull
    private Map<String, Object> parameterSchema;
    @NotNull
    private Map<String, Object> defaultParameters;
    @NotNull
    private Integer status;
}
