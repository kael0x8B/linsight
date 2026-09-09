package com.linsight.module.aivideo.controller.node.node.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;
import lombok.ToString;

@Schema(description = "节点端 - Edge Agent 注册 Request VO")
@Data
public class NodeRegisterReqVO {

    @NotBlank(message = "注册令牌不能为空")
    @Size(max = 128, message = "注册令牌长度不正确")
    @ToString.Exclude
    private String bootstrapToken;

    @NotBlank(message = "节点编码不能为空")
    @Size(max = 64, message = "节点编码不能超过 64 个字符")
    @Pattern(regexp = "^[A-Za-z0-9_-]+$", message = "节点编码只能包含字母、数字、下划线和连字符")
    private String code;

    @NotBlank(message = "节点名称不能为空")
    @Size(max = 100, message = "节点名称不能超过 100 个字符")
    private String name;

    @NotBlank(message = "Agent 版本不能为空")
    @Size(max = 64, message = "Agent 版本不能超过 64 个字符")
    private String agentVersion;

    @NotBlank(message = "主机名不能为空")
    @Size(max = 255, message = "主机名不能超过 255 个字符")
    private String hostName;

}
