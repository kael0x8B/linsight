package com.linsight.module.aivideo.dal.dataobject.rule;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;

import java.time.LocalDateTime;

@TableName("ai_rule_version")
@Data
@EqualsAndHashCode(callSuper = true)
public class RuleVersionDO extends TenantBaseDO {
    @TableId private Long id;
    private Long ruleId;
    private Integer version;
    private String ast;
    private String naturalSummary;
    private String validationStatus;
    private String validationErrors;
    private LocalDateTime publishedTime;
}
