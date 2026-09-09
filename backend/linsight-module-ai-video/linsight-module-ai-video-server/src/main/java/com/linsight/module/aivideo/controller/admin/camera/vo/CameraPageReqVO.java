package com.linsight.module.aivideo.controller.admin.camera.vo;

import com.linsight.framework.common.enums.CommonStatusEnum;
import com.linsight.framework.common.pojo.PageParam;
import com.linsight.framework.common.validation.InEnum;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;
import lombok.EqualsAndHashCode;

@Schema(description = "管理后台 - 摄像头分页 Request VO")
@Data
@EqualsAndHashCode(callSuper = true)
public class CameraPageReqVO extends PageParam {

    @Size(max = 100, message = "摄像头名称不能超过 100 个字符")
    private String name;
    @Size(min=1, max=16)
    private java.util.List<@jakarta.validation.constraints.Positive Long> ids;
    @Size(max = 64, message = "摄像头编码不能超过 64 个字符")
    private String code;
    private Long groupId;
    @Pattern(regexp = "RTSP|ONVIF", message = "接入协议必须是 RTSP 或 ONVIF")
    private String protocol;
    private Integer onlineStatus;
    @InEnum(value = CommonStatusEnum.class, message = "状态必须是 {value}")
    private Integer status;

}
