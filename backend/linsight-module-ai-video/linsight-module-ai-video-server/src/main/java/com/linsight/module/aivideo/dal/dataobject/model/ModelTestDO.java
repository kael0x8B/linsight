package com.linsight.module.aivideo.dal.dataobject.model;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.ToString;

import java.time.LocalDateTime;

@TableName("ai_model_test")
@Data
@EqualsAndHashCode(callSuper = true)
public class ModelTestDO extends TenantBaseDO {
    @TableId private Long id;
    private Long modelVersionId;
    private Long nodeId;
    @ToString.Exclude private String imageRef;
    private String imageName;
    private String parameters;
    private String status;
    private String commandId;
    private String diagnosticId;
    private String backend;
    private Integer preprocessMillis;
    private Integer inferenceMillis;
    private Integer postprocessMillis;
    private String result;
    private String errorCode;
    private String errorMessage;
    private LocalDateTime finishTime;
}
