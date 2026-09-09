package com.linsight.module.aivideo.controller.node.node.vo;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;

import java.util.Map;

@Data
public class NodeCommandReportReqVO {
    @NotBlank
    @Pattern(regexp = "^[0-9a-fA-F-]{36}$")
    private String commandId;
    @NotBlank
    @Pattern(regexp = "RUNNING|SUCCEEDED|FAILED")
    private String status;
    @Pattern(regexp = "REMOVING|REMOVED|DOWNLOADING|VERIFYING|LOADING|READY|INFERENCING|COMPLETED|STARTING|RUNNING|STOPPING|STOPPED|INSTALLING|ACTIVATING|ROLLING_BACK|ROLLED_BACK|RESTARTING|SHUTTING_DOWN|CHECKING_ENV|INSTALLING_DEPS|DOWNLOADING_DEPS|RETRYING_DEPS|VERIFYING_ENV|ENV_READY")
    private String stage;
    @Pattern(regexp = "^[0-9a-fA-F-]{36}$")
    private String diagnosticId;
    @Size(max = 64)
    private String backend;
    @Size(max = 64)
    private String device;
    @Min(0) @Max(600000)
    private Integer preprocessMillis;
    @Min(0) @Max(600000)
    private Integer inferenceMillis;
    @Min(0) @Max(600000)
    private Integer postprocessMillis;
    private Map<String, Object> result;
    @Size(max = 64)
    private String errorCode;
    @Size(max = 500)
    private String errorMessage;
}
