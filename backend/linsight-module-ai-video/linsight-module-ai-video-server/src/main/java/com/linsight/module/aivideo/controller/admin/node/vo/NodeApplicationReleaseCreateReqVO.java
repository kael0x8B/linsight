package com.linsight.module.aivideo.controller.admin.node.vo;

import jakarta.validation.constraints.*;
import lombok.Data;

@Data
public class NodeApplicationReleaseCreateReqVO {
    /** Optional for older clients; the current UI uses the server's default application bundle. */
    @Pattern(regexp="[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}") private String profileId;
    @NotBlank @Pattern(regexp="[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}") private String version;
    @NotBlank @Pattern(regexp="[a-zA-Z0-9-]{16,64}") private String requestId;
    @NotNull @Size(max=4000) private String notes;
    /** Legacy caller declaration. Schema compatibility is checked by the signed bundle installer. */
    @AssertTrue private Boolean backwardCompatible;
}
