package com.linsight.module.aivideo.dal.dataobject.model;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;

@TableName("ai_model")
@Data
@EqualsAndHashCode(callSuper = true)
public class ModelDO extends TenantBaseDO {

    @TableId
    private Long id;
    private String name;
    private String code;
    private String sourceType;
    private String description;
    private Long currentVersionId;
    private Integer status;

}
