package com.linsight.module.aivideo.dal.dataobject.event;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;

import java.time.LocalDateTime;

@TableName("ai_event_outbox")
@Data
@EqualsAndHashCode(callSuper = true)
public class EventOutboxDO extends TenantBaseDO {
    @TableId private Long id;
    private Long eventId;
    private String messageType;
    private String payload;
    private String status;
    private Integer attempts;
    private LocalDateTime nextAttemptTime;
    private LocalDateTime sentTime;
    private String lastError;
}
