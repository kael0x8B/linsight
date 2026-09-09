package com.linsight.module.aivideo.controller.admin.integration.vo;

import io.swagger.v3.oas.annotations.media.Schema;

@Schema(description = "管理后台 - AI 视频模块契约信息 Response VO")
public record AiVideoModuleInfoRespVO(
        @Schema(description = "模块名称", example = "linsight-module-ai-video") String module,
        @Schema(description = "协议版本", example = "1.0") String contractVersion,
        @Schema(description = "运行职责", example = "java-control-plane") String responsibility) {
}
