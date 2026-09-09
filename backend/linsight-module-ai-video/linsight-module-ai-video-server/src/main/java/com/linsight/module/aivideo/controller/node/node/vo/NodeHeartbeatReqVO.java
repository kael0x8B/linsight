package com.linsight.module.aivideo.controller.node.node.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import jakarta.validation.constraints.Pattern;
import lombok.Data;

import java.time.LocalDateTime;

@Schema(description = "节点端 - Edge Agent 心跳 Request VO")
@Data
public class NodeHeartbeatReqVO {

    @NotNull(message = "心跳序号不能为空")
    @Min(value = 1, message = "心跳序号必须从 1 开始递增")
    private Long sequence;

    @NotNull(message = "Agent 时间不能为空")
    private LocalDateTime agentTime;

    @NotBlank(message = "Agent 版本不能为空")
    @Size(max = 64, message = "Agent 版本不能超过 64 个字符")
    private String agentVersion;
    @Pattern(regexp = "v1")
    private String activationGuard;
    @Pattern(regexp = "v1")
    private String modelUninstall;
    private Boolean agentRollbackAvailable;
    @Size(max = 64)
    private String failedAgentVersion;

    @NotBlank(message = "主机名不能为空")
    @Size(max = 255, message = "主机名不能超过 255 个字符")
    private String hostName;

    @Size(max = 64, message = "IP 地址不能超过 64 个字符")
    private String ipAddress;

    @DecimalMin(value = "0.0", message = "CPU 使用率不能小于 0")
    @DecimalMax(value = "100.0", message = "CPU 使用率不能大于 100")
    private Double cpuUsage;

    @Min(value = 0, message = "内存使用量不能小于 0")
    private Long memoryUsedBytes;
    @Min(value = 0, message = "内存总量不能小于 0")
    private Long memoryTotalBytes;
    @Min(value = 0, message = "磁盘使用量不能小于 0")
    private Long diskUsedBytes;
    @Min(value = 0, message = "磁盘总量不能小于 0")
    private Long diskTotalBytes;

    @DecimalMin(value = "0.0", message = "GPU 使用率不能小于 0")
    @DecimalMax(value = "100.0", message = "GPU 使用率不能大于 100")
    private Double gpuUsage;
    @Min(value = 0, message = "GPU 显存使用量不能小于 0")
    private Long gpuMemoryUsedBytes;
    @Min(value = 0, message = "GPU 显存总量不能小于 0")
    private Long gpuMemoryTotalBytes;

    @Pattern(regexp = "UP|DOWN", message = "Runtime 状态必须是 UP 或 DOWN")
    private String runtimeStatus;

    @Size(max = 64, message = "Runtime 诊断编号不能超过 64 个字符")
    private String runtimeDiagnosticId;

}
