package com.linsight.module.aivideo.controller.admin.integration.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;
import lombok.ToString;

import java.util.List;

@Schema(description = "管理后台 - Webhook 端点保存 Request VO")
@Data
public class WebhookSaveReqVO {
    @Schema(description = "端点编号；创建时为空")
    private Long id;

    @NotBlank(message = "端点名称不能为空")
    @Size(max = 100, message = "端点名称不能超过 100 个字符")
    private String name;

    @NotBlank(message = "Webhook 地址不能为空")
    @Size(max = 2048, message = "Webhook 地址不能超过 2048 个字符")
    @Pattern(regexp = "^https://.+", message = "生产 Webhook 地址必须使用 HTTPS")
    private String url;

    @Schema(description = "HMAC 密钥；创建时留空自动生成，修改时留空表示不更换")
    @Size(min = 24, max = 256, message = "签名密钥长度必须在 24 到 256 个字符之间")
    @ToString.Exclude
    private String secret;

    @Size(max = 50, message = "事件类型最多 50 个")
    private List<@Size(max = 64) String> eventTypes;

    @Size(max = 10, message = "事件等级最多 10 个")
    private List<@Size(max = 16) String> severities;

    @NotNull(message = "状态不能为空")
    @Min(value = 0, message = "状态必须为 0 或 1")
    @Max(value = 1, message = "状态必须为 0 或 1")
    private Integer status;

    @NotNull(message = "最大尝试次数不能为空")
    @Min(value = 1, message = "最少尝试 1 次")
    @Max(value = 10, message = "最多尝试 10 次")
    private Integer maxAttempts;

    @NotNull(message = "请求超时不能为空")
    @Min(value = 500, message = "请求超时不能小于 500ms")
    @Max(value = 10000, message = "请求超时不能超过 10000ms")
    private Integer timeoutMs;
}
