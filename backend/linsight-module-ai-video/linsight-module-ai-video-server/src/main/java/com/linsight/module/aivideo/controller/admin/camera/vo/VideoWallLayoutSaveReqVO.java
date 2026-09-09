package com.linsight.module.aivideo.controller.admin.camera.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.Data;

import java.util.List;

@Schema(description = "管理后台 - 视频墙布局方案保存请求")
@Data
public class VideoWallLayoutSaveReqVO {

    private Long id;

    @NotNull(message = "方案位置不能为空")
    @Min(value = 1, message = "方案位置必须在 1 到 15 之间")
    @Max(value = 15, message = "方案位置必须在 1 到 15 之间")
    private Integer slotIndex;

    @NotBlank(message = "方案名称不能为空")
    @Size(max = 50, message = "方案名称不能超过 50 个字符")
    private String name;

    @NotNull(message = "分屏数量不能为空")
    private Integer splitCount;

    @Min(value = 1, message = "边缘节点编号必须大于 0")
    private Long nodeId;

    @NotNull(message = "摄像头位置不能为空")
    @Size(max = 16, message = "摄像头位置不能超过 16 路")
    private List<Long> cameraIds;

}
