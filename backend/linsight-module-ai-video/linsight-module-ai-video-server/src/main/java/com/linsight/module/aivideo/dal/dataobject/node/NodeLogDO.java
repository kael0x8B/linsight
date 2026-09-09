package com.linsight.module.aivideo.dal.dataobject.node;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;

import java.time.LocalDateTime;

@TableName("ai_node_log")
@Data
@EqualsAndHashCode(callSuper = true)
public class NodeLogDO extends TenantBaseDO {
    @TableId
    private Long id;
    private Long nodeId;
    private String entryId;
    private Long taskId;
    private String runId;
    private String component;
    private String level;
    private String message;
    private String contextJson;
    private String diagnosticId;
    private LocalDateTime loggedAt;
}
