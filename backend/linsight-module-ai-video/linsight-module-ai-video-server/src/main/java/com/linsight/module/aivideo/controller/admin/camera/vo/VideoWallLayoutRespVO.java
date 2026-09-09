package com.linsight.module.aivideo.controller.admin.camera.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;
import java.util.List;

@Schema(description = "管理后台 - 视频墙布局方案响应")
@Data
public class VideoWallLayoutRespVO {

    private Long id;
    private Integer slotIndex;
    private String name;
    private Integer splitCount;
    private Long nodeId;
    private String schemaVersion;
    private List<Long> cameraIds;
    private Boolean active;
    private LocalDateTime updateTime;

}
