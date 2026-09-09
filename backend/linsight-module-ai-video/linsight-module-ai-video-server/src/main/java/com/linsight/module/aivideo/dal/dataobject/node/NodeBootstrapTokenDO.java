package com.linsight.module.aivideo.dal.dataobject.node;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.ToString;

import java.time.LocalDateTime;

@TableName("ai_node_bootstrap_token")
@Data
@EqualsAndHashCode(callSuper = true)
public class NodeBootstrapTokenDO extends TenantBaseDO {

    @TableId
    private Long id;
    private String name;
    @ToString.Exclude
    private String tokenDigest;
    private LocalDateTime expireTime;
    private LocalDateTime usedTime;

}
