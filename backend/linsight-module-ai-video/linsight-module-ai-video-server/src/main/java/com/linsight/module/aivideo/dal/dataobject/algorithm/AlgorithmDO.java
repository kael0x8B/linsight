package com.linsight.module.aivideo.dal.dataobject.algorithm;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;

@TableName("ai_algorithm")
@Data
@EqualsAndHashCode(callSuper = true)
public class AlgorithmDO extends TenantBaseDO {
    @TableId
    private Long id;
    private String name;
    private String code;
    private String category;
    private String sceneGroup;
    private String implementationType;
    private String description;
    private String capabilityKey;
    private String requiredCapabilities;
    private String eventType;
    private Long defaultModelId;
    private Long currentPipelineVersionId;
    private String parameterSchema;
    private String defaultParameters;
    private Integer status;
}
