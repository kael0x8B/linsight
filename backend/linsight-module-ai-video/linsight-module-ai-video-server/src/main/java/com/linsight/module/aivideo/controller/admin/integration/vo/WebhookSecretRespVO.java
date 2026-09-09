package com.linsight.module.aivideo.controller.admin.integration.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Data;

@Schema(description = "管理后台 - Webhook 创建结果；签名密钥只返回一次")
@Data
@AllArgsConstructor
public class WebhookSecretRespVO {
    private Long id;
    private String secret;
}
