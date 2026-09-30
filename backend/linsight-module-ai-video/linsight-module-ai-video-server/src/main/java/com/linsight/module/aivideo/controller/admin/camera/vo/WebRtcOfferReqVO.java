package com.linsight.module.aivideo.controller.admin.camera.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Schema(description = "管理后台 - WebRTC 识别同源预览 Offer Request VO")
@Data
public class WebRtcOfferReqVO {

    @NotNull(message = "摄像头编号不能为空")
    @Positive(message = "摄像头编号必须大于 0")
    private Long cameraId;

    @NotNull(message = "边缘节点编号不能为空")
    @Positive(message = "边缘节点编号必须大于 0")
    private Long nodeId;

    @NotBlank(message = "WebRTC Offer SDP 不能为空")
    @Size(max = 1_000_000, message = "WebRTC Offer SDP 不能超过 1000000 字符")
    private String offerSdp;

    @Pattern(regexp = "offer", message = "WebRTC 描述类型必须是 offer")
    private String offerType = "offer";

}
