package com.linsight.module.aivideo.dal.dataobject.event;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.baomidou.mybatisplus.annotation.Version;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;

import java.math.BigDecimal;
import java.time.LocalDateTime;

@TableName("ai_event")
@Data
@EqualsAndHashCode(callSuper = true)
public class EventDO extends TenantBaseDO {
    @TableId private Long id;
    private String eventNo;
    private String sourceEventId;
    private String activityId;
    private String dedupKey;
    private String activeDedupKey;
    private Long taskId;
    private String taskRunId;
    private Long cameraId;
    private Long nodeId;
    private Long algorithmId;
    private Long pipelineVersionId;
    private Long modelVersionId;
    private Long ruleId;
    private Long ruleVersionId;
    private String eventType;
    private String severity;
    private String status;
    private String evidenceStatus;
    private LocalDateTime occurredTime;
    private LocalDateTime firstSeenTime;
    private LocalDateTime lastSeenTime;
    private LocalDateTime closeTime;
    private Long durationMs;
    private BigDecimal maxConfidence;
    private String trackId;
    private Long assigneeId;
    private String handlingResult;
    private String falsePositiveReason;
    private String objectSnapshot;
    private String taskSnapshot;
    private String pipelineSnapshot;
    private String modelSnapshot;
    private String ruleSnapshot;
    @Version private Integer version;
}
