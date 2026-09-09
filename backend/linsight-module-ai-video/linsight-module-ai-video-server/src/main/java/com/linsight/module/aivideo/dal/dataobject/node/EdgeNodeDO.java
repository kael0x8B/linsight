package com.linsight.module.aivideo.dal.dataobject.node;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.ToString;

import java.time.LocalDateTime;

@TableName("ai_edge_node")
@Data
@EqualsAndHashCode(callSuper = true)
public class EdgeNodeDO extends TenantBaseDO {

    @TableId
    private Long id;
    private String code;
    private String name;
    private String agentVersion;
    private String hostName;
    private String ipAddress;
    @ToString.Exclude
    private String credentialDigest;
    private Integer onlineStatus;
    private LocalDateTime lastHeartbeatTime;
    private Long heartbeatSequence;
    private LocalDateTime agentTime;
    private Long clockOffsetMillis;
    private String resourceSnapshot;
    private Integer status;

}
