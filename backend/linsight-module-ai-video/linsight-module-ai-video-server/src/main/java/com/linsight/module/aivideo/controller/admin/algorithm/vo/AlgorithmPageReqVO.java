package com.linsight.module.aivideo.controller.admin.algorithm.vo;

import com.linsight.framework.common.pojo.PageParam;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;
import lombok.EqualsAndHashCode;

@Data
@EqualsAndHashCode(callSuper = true)
public class AlgorithmPageReqVO extends PageParam {
    @Size(max = 100)
    private String name;
    @Size(max = 64)
    private String code;
    @Pattern(regexp = "CORE|EXTENSION|CUSTOM")
    private String category;
    @Pattern(regexp = "^[A-Z][A-Z0-9_]{1,63}$")
    private String sceneGroup;
    @Pattern(regexp = "MODEL_DIRECT|MODEL_FILTER|TRACK_RULE|CLASSICAL_CV|COMPOSITE")
    private String implementationType;
    private Integer status;
}
