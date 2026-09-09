package com.linsight.module.aivideo.controller.node.task.vo;
import jakarta.validation.constraints.*;
import lombok.Data;
@Data public class EntryAutoStartReqVO {
    @NotNull @Positive private Long entryId;
    @NotNull @Positive private Integer version;
    @NotBlank @Pattern(regexp="^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$") private String encounterId;
    @NotNull @Positive private Long observedAtMillis;
}
