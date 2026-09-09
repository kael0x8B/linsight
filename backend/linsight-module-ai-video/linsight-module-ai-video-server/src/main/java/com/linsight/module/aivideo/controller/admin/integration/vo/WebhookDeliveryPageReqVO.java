package com.linsight.module.aivideo.controller.admin.integration.vo;

import com.linsight.framework.common.pojo.PageParam;
import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;
import lombok.EqualsAndHashCode;

@Schema(description = "管理后台 - Webhook 投递分页 Request VO")
@Data
@EqualsAndHashCode(callSuper = true)
public class WebhookDeliveryPageReqVO extends PageParam {
    private Long endpointId;
    private String status;
    private Boolean isTest;
}
