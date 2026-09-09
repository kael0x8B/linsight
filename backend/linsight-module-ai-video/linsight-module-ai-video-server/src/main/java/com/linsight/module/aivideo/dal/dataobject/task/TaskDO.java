package com.linsight.module.aivideo.dal.dataobject.task;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;

import java.time.LocalDateTime;

@TableName("ai_task")
@Data
@EqualsAndHashCode(callSuper = true)
public class TaskDO extends TenantBaseDO {
    @TableId private Long id;
    private String name;
    private String code;
    private Long cameraId;
    private Long algorithmId;
    private Long pipelineVersionId;
    private Long modelVersionId;
    private String modelBindings;
    private Long nodeId;
    private Long ruleId;
    private Long ruleVersionId;
    private String parameters;
    private String desiredStatus;
    private String actualStatus;
    private Integer configVersion;
    private Integer globalSettingsVersion;
    private Integer appliedGlobalSettingsVersion;
    private String globalSettingsSnapshot;
    private String activeRunId;
    private String lastCommandId;
    private LocalDateTime lastHeartbeatTime;
    private String metricsSnapshot;
    private String diagnosticId;
    private String errorCode;
    private String errorMessage;
    private Integer version;
}
