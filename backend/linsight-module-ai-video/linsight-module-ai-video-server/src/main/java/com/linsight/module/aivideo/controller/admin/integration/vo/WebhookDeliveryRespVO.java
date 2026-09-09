package com.linsight.module.aivideo.controller.admin.integration.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.time.LocalDateTime;

@Schema(description = "管理后台 - Webhook 投递记录 Response VO")
@Data
public class WebhookDeliveryRespVO {
    private Long id;
    private Long endpointId;
    private Long eventId;
    private String messageId;
    private String idempotencyKey;
    private String eventType;
    private String severity;
    private String payload;
    private String status;
    private Integer attempts;
    private LocalDateTime nextAttemptTime;
    private LocalDateTime lastAttemptTime;
    private Integer responseStatus;
    private String responseBody;
    private Integer durationMs;
    private String lastError;
    private Boolean isTest;
    private LocalDateTime createTime;
}
