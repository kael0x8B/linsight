package com.linsight.module.aivideo.controller.admin.rule.vo;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
public class RuleSaveReqVO {
    private Long id;
    @NotBlank @Size(max = 100) private String name;
    @NotBlank @Pattern(regexp = "^[a-z][a-z0-9-]{1,63}$") private String code;
    @Size(max = 500) private String description;
    @NotBlank @Pattern(regexp = "^[A-Z][A-Z0-9_]{1,63}$") private String eventType;
    @NotNull private Integer status;
}
