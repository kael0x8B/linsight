package com.linsight.module.aivideo.dal.dataobject.node;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;

import java.time.LocalDateTime;

@TableName("ai_node_deployment")
@Data
@EqualsAndHashCode(callSuper = true)
public class NodeDeploymentDO extends TenantBaseDO {
    @TableId
    private Long id;
    private String requestId;
    private String resourceKey;
    private String executorOwner;
    private String logStatus;
    private Boolean logTruncated;
    private String controlPlaneUrl;
    private String previousVersion;
    private String targetVersion;
    private String host;
    private Integer port;
    private String username;
    private String nodeCode;
    private String nodeName;
    private String operationType;
    private String targetArch;
    private String osSummary;
    private String pythonVersion;
    private String runtimePackageSha256;
    private String status;
    private String stage;
    private Integer progress;
    private String message;
    private String outputLog;
    private String diagnosticId;
    private Long edgeNodeId;
    private LocalDateTime finishTime;
}
