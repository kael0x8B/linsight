package com.linsight.module.aivideo.controller.admin.algorithm.vo;

import com.linsight.framework.common.pojo.PageParam;
import jakarta.validation.constraints.Pattern;
import lombok.Data;
import lombok.EqualsAndHashCode;

@Data
@EqualsAndHashCode(callSuper = true)
public class RecognitionLibraryPageReqVO extends PageParam {
    private String name;
    @Pattern(regexp = "FACE|PLATE|POSE")
    private String libraryType;
    private Integer status;
}
