package com.linsight.module.aivideo.controller.admin.event.vo;

import com.linsight.framework.common.pojo.PageParam;
import lombok.Data;
import lombok.EqualsAndHashCode;
import org.springframework.format.annotation.DateTimeFormat;

import java.time.LocalDateTime;

import static com.linsight.framework.common.util.date.DateUtils.FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND;

@Data
@EqualsAndHashCode(callSuper = true)
public class EventPageReqVO extends PageParam {
    private String eventNo;
    private Long taskId;
    private Long algorithmId;
    private Long cameraId;
    private String eventType;
    private String severity;
    private String status;
    @DateTimeFormat(pattern = FORMAT_YEAR_MONTH_DAY_HOUR_MINUTE_SECOND)
    private LocalDateTime[] occurredTime;
}
