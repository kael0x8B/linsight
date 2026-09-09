package com.linsight.module.aivideo.controller.admin.node.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
public class NodeDeploymentConnectionReqVO {
    @jakarta.validation.constraints.Positive
    private Long nodeId;
    @Schema(description = "网关 IP 或主机名", example = "192.168.2.17")
    @NotBlank @Size(max = 255) @Pattern(regexp = "[A-Za-z0-9._:-]+")
    private String host;
    @jakarta.validation.constraints.NotNull @Min(1) @Max(65535)
    private Integer port = 22;
    @NotBlank @Pattern(regexp = "[A-Za-z_][A-Za-z0-9_-]{0,31}")
    private String username;
    @NotBlank @Size(max = 256) @Pattern(regexp = "[^\\r\\n]+")
    @lombok.ToString.Exclude
    private String password;
}
