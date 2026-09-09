package com.linsight.module.aivideo.controller.admin.node.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Schema(description = "管理后台 - 节点一次性注册令牌创建 Request VO")
@Data
public class NodeBootstrapTokenCreateReqVO {

    @Schema(description = "用途说明", requiredMode = Schema.RequiredMode.REQUIRED, example = "一号边缘服务器")
    @NotBlank(message = "用途说明不能为空")
    @Size(max = 100, message = "用途说明不能超过 100 个字符")
    private String name;

    @Schema(description = "有效分钟数", requiredMode = Schema.RequiredMode.REQUIRED, example = "30")
    @NotNull(message = "有效分钟数不能为空")
    @Min(value = 5, message = "有效期不能少于 5 分钟")
    @Max(value = 1440, message = "有效期不能超过 1440 分钟")
    private Integer ttlMinutes;

}
