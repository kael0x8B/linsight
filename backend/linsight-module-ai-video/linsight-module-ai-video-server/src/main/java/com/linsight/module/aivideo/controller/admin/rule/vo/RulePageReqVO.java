package com.linsight.module.aivideo.controller.admin.rule.vo;

import com.linsight.framework.common.pojo.PageParam;
import jakarta.validation.constraints.Size;
import lombok.Data;
import lombok.EqualsAndHashCode;

@Data
@EqualsAndHashCode(callSuper = true)
public class RulePageReqVO extends PageParam {
    @Size(max = 100) private String name;
    @Size(max = 64) private String code;
    @Size(max = 64) private String eventType;
    private Integer status;
}
