package com.linsight.module.aivideo.controller.admin.node.vo;

import com.linsight.framework.common.pojo.PageParam;
import lombok.Data;
import lombok.EqualsAndHashCode;
import org.springframework.format.annotation.DateTimeFormat;

import java.time.LocalDateTime;

import static com.linsight.framework.common.util.date.DateUtils.FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND;

@Data
@EqualsAndHashCode(callSuper = true)
public class NodeLogPageReqVO extends PageParam {
    private Long nodeId;
    private Long taskId;
    private String component;
    private String level;
    private String keyword;
    private String diagnosticId;
    @jakarta.validation.constraints.PositiveOrZero
    private Long snapshotMaxId;
    @jakarta.validation.constraints.PositiveOrZero
    private Long afterId;
    @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
    private LocalDateTime[] loggedAt;
}
