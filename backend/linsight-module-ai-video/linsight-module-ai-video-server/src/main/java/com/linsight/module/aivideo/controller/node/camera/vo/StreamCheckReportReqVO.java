package com.linsight.module.aivideo.controller.node.camera.vo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import lombok.Data;

import java.util.List;

@Data
public class StreamCheckReportReqVO {

    @NotNull(message = "检测任务编号不能为空")
    @Positive(message = "检测任务编号必须大于 0")
    private Long checkId;

    @NotNull(message = "检测在线结果不能为空")
    private Boolean online;

    @NotNull(message = "诊断编号不能为空")
    @Pattern(regexp = "^[0-9a-fA-F-]{36}$", message = "诊断编号格式不正确")
    private String diagnosticId;

    @Valid
    @Size(min = 1, max = 5, message = "检测阶段数量必须为 1 到 5")
    private List<StreamCheckStageReqVO> stages;

    @Valid
    private StreamInfoReqVO stream;

    @Size(max = 64, message = "错误码不能超过 64 个字符")
    private String errorCode;

    @Size(max = 500, message = "错误摘要不能超过 500 个字符")
    private String errorMessage;

}
