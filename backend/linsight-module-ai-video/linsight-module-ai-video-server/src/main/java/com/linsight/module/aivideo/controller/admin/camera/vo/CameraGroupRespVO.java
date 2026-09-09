package com.linsight.module.aivideo.controller.admin.camera.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;

@Schema(description = "管理后台 - 摄像头分组 Response VO")
@Data
public class CameraGroupRespVO {

    private Long id;
    private String name;
    private Long parentId;
    private String path;
    private Integer sort;
    private Integer status;
    private LocalDateTime createTime;

}
