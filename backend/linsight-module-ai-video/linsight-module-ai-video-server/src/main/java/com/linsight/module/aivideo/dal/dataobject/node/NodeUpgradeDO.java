package com.linsight.module.aivideo.dal.dataobject.node;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;

import java.time.LocalDateTime;

@TableName("ai_node_upgrade")
@Data
@EqualsAndHashCode(callSuper = true)
public class NodeUpgradeDO extends TenantBaseDO {
    @TableId
    private Long id;
    private Long nodeId;
    private String action;
    private String targetVersion;
    private String packageRef;
    private String packageName;
    private String sha256;
    private String signature;
    private String commandId;
    private Integer configVersion;
    private String status;
    private String stage;
    private String diagnosticId;
    private String resultSummary;
    private String errorCode;
    private String errorMessage;
    private LocalDateTime finishTime;
    private LocalDateTime activationRequestedAt;
    private String previousVersion;
}
