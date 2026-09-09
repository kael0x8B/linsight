package com.linsight.module.aivideo.controller.admin.node.vo;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;
import lombok.EqualsAndHashCode;

@Data
@EqualsAndHashCode(callSuper = true)
public class NodeDeploymentCreateReqVO extends NodeDeploymentConnectionReqVO {
    @Size(max = 64) @Pattern(regexp = "[A-Za-z0-9_-]+")
    private String requestId;
    @Pattern(regexp = "DEPLOY|ROLLBACK")
    private String action = "DEPLOY";
    @NotBlank @Pattern(regexp = "[A-Za-z0-9_-]{1,64}")
    private String nodeCode;
    @NotBlank @Size(max = 100) @Pattern(regexp = "[^\\r\\n]+")
    private String nodeName;
    @NotBlank @Size(max = 512) @Pattern(regexp = "https?://[^\\s]+")
    private String controlPlaneUrl;
    @NotBlank @Size(max = 64) @Pattern(regexp = "[A-Za-z0-9@._+-]+")
    private String hostKeyType;
    @NotBlank @Size(max = 4096) @Pattern(regexp = "[A-Za-z0-9+/=]+")
    private String hostKey;
    @NotBlank @Size(max = 256) @Pattern(regexp = "[A-Za-z0-9:+/=_-]+")
    private String hostKeyFingerprint;
    private Boolean installDependencies = true;
}
