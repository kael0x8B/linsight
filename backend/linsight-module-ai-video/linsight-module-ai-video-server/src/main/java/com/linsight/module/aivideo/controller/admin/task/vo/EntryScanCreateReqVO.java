package com.linsight.module.aivideo.controller.admin.task.vo;
import lombok.Data;
import jakarta.validation.constraints.*;
@Data public class EntryScanCreateReqVO {
    @NotNull @Positive private Long entryAccessId;
    @NotNull @AssertTrue private Boolean consentConfirmed;
}
