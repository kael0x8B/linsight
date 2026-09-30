package com.linsight.module.aivideo.controller.admin.camera.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import lombok.Data;

@Schema(description = "管理后台 - 单路预览会话创建 Request VO")
@Data
public class PreviewSessionCreateReqVO {

    @NotNull(message = "摄像头编号不能为空")
    @Positive(message = "摄像头编号必须大于 0")
    private Long cameraId;

    @NotNull(message = "边缘节点编号不能为空")
    @Positive(message = "边缘节点编号必须大于 0")
    private Long nodeId;

    @Schema(description = "无运行识别任务时使用的码流；有任务时跟随识别码流", example = "SUB")
    @Pattern(regexp = "MAIN|SUB", message = "码流类型必须是 MAIN 或 SUB")
    private String streamType = "SUB";

}
