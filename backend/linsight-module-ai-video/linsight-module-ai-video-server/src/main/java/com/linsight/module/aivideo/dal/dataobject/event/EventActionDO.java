package com.linsight.module.aivideo.dal.dataobject.event;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;

@TableName("ai_event_action")
@Data
@EqualsAndHashCode(callSuper = true)
public class EventActionDO extends TenantBaseDO {
    @TableId private Long id;
    private Long eventId;
    private String actionType;
    private String fromStatus;
    private String toStatus;
    private Long operatorId;
    private Long assigneeId;
    private String remark;
    private String reasonCode;
}
