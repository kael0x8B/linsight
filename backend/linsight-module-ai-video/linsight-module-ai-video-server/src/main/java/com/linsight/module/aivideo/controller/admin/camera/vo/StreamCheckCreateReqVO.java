package com.linsight.module.aivideo.controller.admin.camera.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import lombok.Data;

@Schema(description = "管理后台 - 摄像头异步连通检测创建 Request VO")
@Data
public class StreamCheckCreateReqVO {

    @NotNull(message = "摄像头编号不能为空")
    @Positive(message = "摄像头编号必须大于 0")
    private Long cameraId;

    @NotNull(message = "执行节点编号不能为空")
    @Positive(message = "执行节点编号必须大于 0")
    private Long nodeId;

}
