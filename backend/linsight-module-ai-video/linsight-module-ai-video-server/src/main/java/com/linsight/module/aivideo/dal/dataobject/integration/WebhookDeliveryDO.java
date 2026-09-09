package com.linsight.module.aivideo.dal.dataobject.integration;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;

import java.time.LocalDateTime;

@TableName("ai_webhook_delivery")
@Data
@EqualsAndHashCode(callSuper = true)
public class WebhookDeliveryDO extends TenantBaseDO {
    @TableId
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
}
