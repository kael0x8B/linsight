package com.linsight.module.aivideo.controller.admin.integration.vo;

import com.linsight.framework.common.pojo.PageParam;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

@Schema(description = "管理后台 - Webhook 端点分页 Request VO")
@Data
@EqualsAndHashCode(callSuper = true)
public class WebhookPageReqVO extends PageParam {
    @Schema(description = "名称关键字")
    private String name;
    @Schema(description = "状态：0 启用，1 停用")
    private Integer status;
}
