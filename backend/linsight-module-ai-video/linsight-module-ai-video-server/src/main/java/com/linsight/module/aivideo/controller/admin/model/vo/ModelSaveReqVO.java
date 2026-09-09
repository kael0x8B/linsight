package com.linsight.module.aivideo.controller.admin.model.vo;

import com.linsight.framework.common.enums.CommonStatusEnum;
import com.linsight.framework.common.validation.InEnum;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Schema(description = "管理后台 - 模型资产创建/修改 Request VO")
@Data
public class ModelSaveReqVO {

    private Long id;

    @NotBlank(message = "模型名称不能为空")
    @Size(max = 100, message = "模型名称不能超过 100 个字符")
    private String name;

    @NotBlank(message = "模型编码不能为空")
    @Size(max = 64, message = "模型编码不能超过 64 个字符")
    @Pattern(regexp = "^[a-z0-9][a-z0-9-]*$", message = "模型编码只能包含小写字母、数字和连字符")
    private String code;

    @NotBlank(message = "来源类型不能为空")
    @Pattern(regexp = "PRESET|CUSTOM", message = "来源类型必须是 PRESET 或 CUSTOM")
    private String sourceType;

    @Size(max = 500, message = "模型说明不能超过 500 个字符")
    private String description;

    @NotNull(message = "状态不能为空")
    @InEnum(value = CommonStatusEnum.class, message = "状态必须是 {value}")
    private Integer status;

}
