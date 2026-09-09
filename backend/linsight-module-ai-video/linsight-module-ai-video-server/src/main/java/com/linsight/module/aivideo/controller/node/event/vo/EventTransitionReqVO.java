package com.linsight.module.aivideo.controller.node.event.vo;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;

import java.time.LocalDateTime;

@Data
public class EventTransitionReqVO {
    @NotBlank @Size(max = 64) private String sourceEventId;
    @NotBlank @Pattern(regexp = "RECOVERED|CLOSED") private String state;
    @NotNull private LocalDateTime occurredTime;
}
