package com.linsight.module.aivideo.dal.dataobject.node;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;

import java.time.LocalDateTime;

@TableName("ai_node_command")
@Data
@EqualsAndHashCode(callSuper = true)
public class NodeCommandDO extends TenantBaseDO {
    @TableId
    private Long id;
    private String commandId;
    private Long nodeId;
    private String commandType;
    private Long aggregateId;
    private Integer configVersion;
    private String idempotencyKey;
    private String status;
    private Integer attemptCount;
    private String resultSummary;
    private String errorCode;
    private String errorMessage;
    private LocalDateTime expireTime;
    private LocalDateTime sentTime;
    private LocalDateTime finishTime;
}
