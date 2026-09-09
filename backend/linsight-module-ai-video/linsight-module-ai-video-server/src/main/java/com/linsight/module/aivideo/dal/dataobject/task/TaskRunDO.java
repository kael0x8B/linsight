package com.linsight.module.aivideo.dal.dataobject.task;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;

import java.time.LocalDateTime;

@TableName("ai_task_run")
@Data
@EqualsAndHashCode(callSuper = true)
public class TaskRunDO extends TenantBaseDO {
    @TableId private Long id;
    private Long taskId;
    private String runId;
    private Integer configVersion;
    private String commandId;
    private String status;
    private LocalDateTime startTime;
    private LocalDateTime finishTime;
    private String metricsSnapshot;
    private String diagnosticId;
    private String errorCode;
    private String errorMessage;
}
