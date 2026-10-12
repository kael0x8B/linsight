package com.linsight.module.aivideo.controller.admin.task.vo;

import com.linsight.framework.common.pojo.PageParam;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import lombok.Data;
import lombok.EqualsAndHashCode;

@Data
@EqualsAndHashCode(callSuper = true)
public class TaskEvaluationPageReqVO extends PageParam {
    @Positive private Long taskId;
    @Pattern(regexp = "PASS|FAIL") private String status;
}
