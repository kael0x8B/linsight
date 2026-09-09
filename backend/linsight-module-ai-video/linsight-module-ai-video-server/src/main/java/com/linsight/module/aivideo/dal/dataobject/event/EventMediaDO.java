package com.linsight.module.aivideo.dal.dataobject.event;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;

import java.time.LocalDateTime;

@TableName("ai_event_media")
@Data
@EqualsAndHashCode(callSuper = true)
public class EventMediaDO extends TenantBaseDO {
    @TableId private Long id;
    private Long eventId;
    private String mediaType;
    private String objectRef;
    private String fileName;
    private String mimeType;
    private Long fileSize;
    private String sha256;
    private String status;
    private String errorMessage;
    private LocalDateTime captureStartTime;
    private LocalDateTime captureEndTime;
}
