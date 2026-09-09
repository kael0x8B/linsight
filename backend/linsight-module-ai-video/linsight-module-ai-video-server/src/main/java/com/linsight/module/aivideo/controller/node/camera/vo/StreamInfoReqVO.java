package com.linsight.module.aivideo.controller.node.camera.vo;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
public class StreamInfoReqVO {

    @Size(max = 32, message = "编码名称不能超过 32 个字符")
    private String codec;
    @Min(value = 1, message = "视频宽度必须大于 0")
    private Integer width;
    @Min(value = 1, message = "视频高度必须大于 0")
    private Integer height;
    @Size(max = 32, message = "帧率不能超过 32 个字符")
    private String averageFrameRate;

}
