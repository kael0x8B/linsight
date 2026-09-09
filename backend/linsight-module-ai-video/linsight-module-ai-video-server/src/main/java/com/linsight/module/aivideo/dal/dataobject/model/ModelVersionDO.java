package com.linsight.module.aivideo.dal.dataobject.model;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.ToString;

import java.time.LocalDateTime;

@TableName("ai_model_version")
@Data
@EqualsAndHashCode(callSuper = true)
public class ModelVersionDO extends TenantBaseDO {

    @TableId
    private Long id;
    private Long modelId;
    private String version;
    private String sourceRepository;
    private String sourceRevision;
    @ToString.Exclude
    private String artifactRef;
    private String artifactName;
    private String artifactFormat;
    private String runtimeManifest;
    private Long artifactSize;
    private String sha256;
    private String licenseSpdx;
    private String validationStatus;
    private String publishStatus;
    private String executionStatus;
    private LocalDateTime executionReadyTime;
    private LocalDateTime publishedTime;

}
