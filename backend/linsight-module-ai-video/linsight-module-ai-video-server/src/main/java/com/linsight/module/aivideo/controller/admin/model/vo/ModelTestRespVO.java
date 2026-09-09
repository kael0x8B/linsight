package com.linsight.module.aivideo.controller.admin.model.vo;

import lombok.Data;
import java.time.LocalDateTime;

@Data
public class ModelTestRespVO {
    private Long id;
    private Long modelVersionId;
    private Long nodeId;
    private String imageName;
    private String parameters;
    private String status;
    private String commandId;
    private String diagnosticId;
    private String backend;
    private Integer preprocessMillis;
    private Integer inferenceMillis;
    private Integer postprocessMillis;
    private String result;
    private String errorCode;
    private String errorMessage;
    private LocalDateTime finishTime;
    private LocalDateTime createTime;
}
