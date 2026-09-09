package com.linsight.module.aivideo.dal.dataobject.node;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;

import java.time.LocalDateTime;

@TableName("ai_node_diagnostic_bundle")
@Data
@EqualsAndHashCode(callSuper = true)
public class NodeDiagnosticBundleDO extends TenantBaseDO {
    @TableId
    private Long id;
    private Long nodeId;
    private Long taskId;
    private LocalDateTime rangeStart;
    private LocalDateTime rangeEnd;
    private String status;
    private String fileRef;
    private String fileName;
    private Integer logCount;
    private LocalDateTime expiresAt;
    private String errorMessage;
}
