package com.linsight.module.aivideo.controller.admin.camera.vo;

import com.linsight.framework.common.enums.CommonStatusEnum;
import com.linsight.framework.common.validation.InEnum;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Schema(description = "管理后台 - 摄像头分组列表 Request VO")
@Data
public class CameraGroupListReqVO {

    @Schema(description = "分组名称", example = "厂区")
    @Size(max = 100, message = "分组名称不能超过 100 个字符")
    private String name;

    @Schema(description = "状态", example = "0")
    @InEnum(value = CommonStatusEnum.class, message = "状态必须是 {value}")
    private Integer status;

}
