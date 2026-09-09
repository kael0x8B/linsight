package com.linsight.module.aivideo.controller.admin.camera.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

@Schema(description = "管理后台 - 单路预览会话 Response VO")
@Data
public class PreviewSessionRespVO {

    private String sessionId;
    private Long cameraId;
    private Long nodeId;
    private String protocol;
    private String state;
    private Integer subscriberCount;
    private String diagnosticId;
    private String manifestUrl;
    private String answerSdp;
    private String answerType;
    private String overlayMessageType;

}
