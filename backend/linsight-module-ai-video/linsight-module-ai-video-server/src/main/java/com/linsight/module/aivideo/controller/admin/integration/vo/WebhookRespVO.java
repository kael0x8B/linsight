package com.linsight.module.aivideo.controller.admin.integration.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;
import java.util.List;

@Schema(description = "管理后台 - Webhook 端点 Response VO")
@Data
public class WebhookRespVO {
    private Long id;
    private String name;
    private String url;
    private String secretMasked;
    private List<String> eventTypes;
    private List<String> severities;
    private Integer status;
    private Integer maxAttempts;
    private Integer timeoutMs;
    private Long successCount;
    private Long failureCount;
    private Double successRate;
    private LocalDateTime lastSuccessTime;
    private LocalDateTime lastFailureTime;
    private String lastError;
    private LocalDateTime createTime;
}
