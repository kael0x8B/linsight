package com.linsight.module.aivideo.controller.admin.camera.vo;

import com.linsight.framework.common.enums.CommonStatusEnum;
import com.linsight.framework.common.validation.InEnum;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Schema(description = "管理后台 - 摄像头分组创建/修改 Request VO")
@Data
public class CameraGroupSaveReqVO {

    @Schema(description = "分组编号", example = "1024")
    private Long id;

    @Schema(description = "分组名称", requiredMode = Schema.RequiredMode.REQUIRED, example = "厂区一")
    @NotBlank(message = "分组名称不能为空")
    @Size(max = 100, message = "分组名称不能超过 100 个字符")
    private String name;

    @Schema(description = "父分组编号，根分组为 0", example = "0")
    private Long parentId;

    @Schema(description = "显示顺序", requiredMode = Schema.RequiredMode.REQUIRED, example = "10")
    @NotNull(message = "显示顺序不能为空")
    @Min(value = 0, message = "显示顺序不能小于 0")
    private Integer sort;

    @Schema(description = "状态", requiredMode = Schema.RequiredMode.REQUIRED, example = "0")
    @NotNull(message = "状态不能为空")
    @InEnum(value = CommonStatusEnum.class, message = "状态必须是 {value}")
    private Integer status;

}
