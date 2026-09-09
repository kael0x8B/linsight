package com.linsight.module.aivideo.controller.admin.camera.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;

@Schema(description = "管理后台 - 摄像头异步连通检测 Response VO")
@Data
public class StreamCheckRespVO {

    private Long id;
    private Long cameraId;
    private Long nodeId;
    private String status;
    private String diagnosticId;
    private String stageResults;
    private String streamInfo;
    private String errorCode;
    private String errorMessage;
    private LocalDateTime startTime;
    private LocalDateTime finishTime;
    private LocalDateTime createTime;

}
