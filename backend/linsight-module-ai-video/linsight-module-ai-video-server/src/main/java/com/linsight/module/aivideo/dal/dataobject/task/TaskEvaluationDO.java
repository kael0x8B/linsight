package com.linsight.module.aivideo.dal.dataobject.task;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;

@TableName("ai_task_evaluation")
@Data
@EqualsAndHashCode(callSuper = true)
public class TaskEvaluationDO extends TenantBaseDO {
    @TableId private Long id;
    private Long taskId;
    private String taskName;
    private Integer configVersion;
    private String requestId;
    private String requestHash;
    private String source;
    private String status;
    private String datasetVersion;
    private String datasetSha256;
    private Long measuredAtMillis;
    private String evidenceRef;
    private String measurement;
    private String configurationSnapshot;
    private String failedChecks;
}
