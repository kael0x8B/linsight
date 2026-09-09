package com.linsight.module.aivideo.dal.dataobject.integration;

import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.mybatis.core.type.EncryptTypeHandler;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.ToString;

import java.time.LocalDateTime;

@TableName(value = "ai_webhook_endpoint", autoResultMap = true)
@Data
@EqualsAndHashCode(callSuper = true)
public class WebhookEndpointDO extends TenantBaseDO {
    @TableId
    private Long id;
    private String name;
    private String url;
    @TableField(value = "secret_ciphertext", typeHandler = EncryptTypeHandler.class)
    @ToString.Exclude
    private String secret;
    private String eventTypesJson;
    private String severitiesJson;
    private Integer status;
    private Integer maxAttempts;
    private Integer timeoutMs;
    private Long successCount;
    private Long failureCount;
    private LocalDateTime lastSuccessTime;
    private LocalDateTime lastFailureTime;
    private String lastError;
}
