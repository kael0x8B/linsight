package com.linsight.module.aivideo.controller.admin.node.vo;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import lombok.Data;
import org.springframework.web.multipart.MultipartFile;

@Data
public class NodeUpgradeCreateReqVO {
    @NotNull @Positive
    private Long nodeId;
    @NotBlank
    @Size(max = 64)
    @Pattern(regexp = "^[A-Za-z0-9._-]+$")
    private String targetVersion;
    @NotBlank
    @Pattern(regexp = "^[0-9a-f]{64}$")
    private String signature;
    @NotNull
    private MultipartFile file;
}
