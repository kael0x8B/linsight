package com.linsight.module.aivideo.controller.admin.model.vo;

import com.linsight.framework.common.enums.CommonStatusEnum;
import com.linsight.framework.common.pojo.PageParam;
import com.linsight.framework.common.validation.InEnum;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;
import lombok.EqualsAndHashCode;

@Data
@EqualsAndHashCode(callSuper = true)
public class ModelPageReqVO extends PageParam {

    @Size(max = 100)
    private String name;
    @Size(max = 64)
    private String code;
    @Pattern(regexp = "PRESET|CUSTOM")
    private String sourceType;
    @Pattern(regexp = "ONNX|TORCHSCRIPT|PYTORCH|TENSORRT|RKNN|ARCHIVE")
    private String artifactFormat;
    @Pattern(regexp = "DRAFT|PUBLISHED|SUPERSEDED")
    private String publishStatus;
    @InEnum(value = CommonStatusEnum.class, message = "状态必须是 {value}")
    private Integer status;

}
