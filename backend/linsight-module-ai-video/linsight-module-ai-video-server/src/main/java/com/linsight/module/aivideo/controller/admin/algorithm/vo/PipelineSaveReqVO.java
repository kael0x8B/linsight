package com.linsight.module.aivideo.controller.admin.algorithm.vo;

import jakarta.validation.constraints.NotNull;
import lombok.Data;

import java.util.Map;

@Data
public class PipelineSaveReqVO {
    @NotNull
    private Long algorithmId;
    @NotNull
    private Map<String, Object> dag;
}
