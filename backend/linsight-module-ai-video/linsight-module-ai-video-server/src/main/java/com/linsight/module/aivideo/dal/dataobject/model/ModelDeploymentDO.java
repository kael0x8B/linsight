package com.linsight.module.aivideo.dal.dataobject.model;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;

import java.time.LocalDateTime;

@TableName("ai_model_deployment")
@Data
@EqualsAndHashCode(callSuper = true)
public class ModelDeploymentDO extends TenantBaseDO {
    @TableId private Long id;
    private Long modelVersionId;
    private Long nodeId;
    private Integer configVersion;
    private String desiredStatus;
    private String actualStatus;
    private String commandId;
    private String diagnosticId;
    private String backend;
    private String device;
    private String errorCode;
    private String errorMessage;
    private LocalDateTime readyTime;
}
