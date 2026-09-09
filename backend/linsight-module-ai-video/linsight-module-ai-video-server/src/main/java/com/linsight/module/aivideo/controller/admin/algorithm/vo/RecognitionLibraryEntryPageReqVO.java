package com.linsight.module.aivideo.controller.admin.algorithm.vo;

import com.linsight.framework.common.pojo.PageParam;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import lombok.Data;
import lombok.EqualsAndHashCode;

@Data
@EqualsAndHashCode(callSuper = true)
public class RecognitionLibraryEntryPageReqVO extends PageParam {
    @NotNull private Long libraryId;
    private String name;
    @Pattern(regexp = "PENDING|READY|FAILED") private String featureStatus;
    private Integer status;
}
