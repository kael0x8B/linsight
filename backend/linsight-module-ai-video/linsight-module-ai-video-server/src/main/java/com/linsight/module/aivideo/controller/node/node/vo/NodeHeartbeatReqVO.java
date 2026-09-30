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

    @jakarta.validation.Valid
    private ModelEnvironment modelEnvironment;

    @Data
    public static class ModelEnvironment {
        @NotBlank
        @Pattern(regexp = "1\\.0")
        private String schemaVersion;
        @NotNull
        @Size(max = 16)
        private java.util.List<@NotBlank @Pattern(regexp = "[A-Z][A-Z0-9_]{0,31}") String> formats;
        @NotNull
        @Size(max = 8)
        private java.util.List<@NotBlank @Pattern(regexp = "rk[0-9]{4}[a-z]?") String> rknnTargets;
        @jakarta.validation.Valid
        @Size(max = 16)
        private java.util.List<ExecutionProvider> providers;

        @Data
        public static class ExecutionProvider {
            @NotBlank
            @Size(max = 64)
            @Pattern(regexp = "[a-z0-9][a-z0-9._-]{0,63}")
            private String code;
            @NotBlank
            @Pattern(regexp = "CPU|GPU|NPU|ACCELERATOR")
            private String deviceType;
            @NotBlank
            @Size(max = 64)
            @Pattern(regexp = "[a-z0-9][a-z0-9._-]{0,63}")
            private String vendor;
            @NotNull
            @Size(max = 16)
            private java.util.List<@NotBlank @Pattern(regexp = "[A-Za-z0-9][A-Za-z0-9._-]{0,63}") String> targets;
            @NotNull
            @Size(max = 16)
            private java.util.List<@NotBlank @Pattern(regexp = "[A-Z][A-Z0-9_]{0,31}") String> formats;
            @NotBlank
            @Size(max = 64)
            @Pattern(regexp = "[a-z0-9][a-z0-9._-]{0,63}")
            private String runtime;
            @Size(max = 64)
            @Pattern(regexp = "[0-9A-Za-z][0-9A-Za-z.+_-]{0,63}")
            private String runtimeVersion;
        }
    }

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
    private String algorithmPackageSdk;
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

    @DecimalMin(value = "0.0", message = "NPU 使用率不能小于 0")
    @DecimalMax(value = "100.0", message = "NPU 使用率不能大于 100")
    private Double npuUsage;

    @Pattern(regexp = "RECLAIMED|STILL_HIGH", message = "磁盘处置状态无效")
    private String diskCleanupStatus;
    @Min(value = 0, message = "磁盘处置时间不能小于 0")
    private Long diskCleanupLastRunEpochSeconds;
    @Min(value = 0, message = "磁盘处置前使用率不能小于 0")
    @jakarta.validation.constraints.Max(value = 100, message = "磁盘处置前使用率不能大于 100")
    private Integer diskCleanupBeforePercent;
    @Min(value = 0, message = "磁盘处置后使用率不能小于 0")
    @jakarta.validation.constraints.Max(value = 100, message = "磁盘处置后使用率不能大于 100")
    private Integer diskCleanupAfterPercent;
    @Min(value = 0, message = "磁盘回收字节数不能小于 0")
    private Long diskCleanupFreedBytes;
    @Size(max = 255, message = "磁盘处置动作不能超过 255 个字符")
    @Pattern(regexp = "[a-z_,]+", message = "磁盘处置动作格式无效")
    private String diskCleanupActions;

    @Pattern(regexp = "UP|DOWN", message = "Runtime 状态必须是 UP 或 DOWN")
    private String runtimeStatus;

    @Size(max = 64, message = "Runtime 诊断编号不能超过 64 个字符")
    private String runtimeDiagnosticId;

}
