package com.linsight.module.aivideo.dal.dataobject.algorithm;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;

import java.time.LocalDateTime;

@TableName("ai_pipeline_version")
@Data
@EqualsAndHashCode(callSuper = true)
public class PipelineVersionDO extends TenantBaseDO {
    @TableId
    private Long id;
    private Long algorithmId;
    private Integer version;
    private String dag;
    private String validationStatus;
    private String validationErrors;
    private LocalDateTime publishedTime;
}
