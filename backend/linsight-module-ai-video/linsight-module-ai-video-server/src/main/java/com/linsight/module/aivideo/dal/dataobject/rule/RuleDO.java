package com.linsight.module.aivideo.dal.dataobject.rule;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;

@TableName("ai_rule")
@Data
@EqualsAndHashCode(callSuper = true)
public class RuleDO extends TenantBaseDO {
    @TableId private Long id;
    private String name;
    private String code;
    private String description;
    private String eventType;
    private Long currentVersionId;
    private Integer status;
}
