package com.linsight.module.aivideo.controller.admin.camera.vo;

import com.linsight.framework.common.enums.CommonStatusEnum;
import com.linsight.framework.common.validation.InEnum;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;
import lombok.ToString;

@Schema(description = "管理后台 - 摄像头创建/修改 Request VO")
@Data
public class CameraSaveReqVO {

    @Schema(description = "摄像头编号", example = "1024")
    private Long id;

    @Schema(description = "摄像头名称", requiredMode = Schema.RequiredMode.REQUIRED, example = "一号门岗")
    @NotBlank(message = "摄像头名称不能为空")
    @Size(max = 100, message = "摄像头名称不能超过 100 个字符")
    private String name;

    @Schema(description = "租户内稳定编码", requiredMode = Schema.RequiredMode.REQUIRED, example = "CAM-GATE-001")
    @NotBlank(message = "摄像头编码不能为空")
    @Size(max = 64, message = "摄像头编码不能超过 64 个字符")
    @Pattern(regexp = "^[A-Za-z0-9_-]+$", message = "摄像头编码只能包含字母、数字、下划线和连字符")
    private String code;

    @Schema(description = "分组编号，未分组为 0", example = "0")
    @Min(value = 0, message = "分组编号不能小于 0")
    private Long groupId;

    @Schema(description = "接入协议", requiredMode = Schema.RequiredMode.REQUIRED, example = "RTSP")
    @NotBlank(message = "接入协议不能为空")
    @Pattern(regexp = "RTSP|ONVIF", message = "接入协议必须是 RTSP 或 ONVIF")
    private String protocol;

    @Schema(description = "设备主机名或 IP，不含凭据", requiredMode = Schema.RequiredMode.REQUIRED, example = "192.168.1.20")
    @NotBlank(message = "设备主机不能为空")
    @Size(max = 255, message = "设备主机不能超过 255 个字符")
    @Pattern(regexp = "^[A-Za-z0-9._:\\[\\]-]+$", message = "设备主机格式不正确")
    private String host;

    @Schema(description = "设备端口", requiredMode = Schema.RequiredMode.REQUIRED, example = "554")
    @NotNull(message = "设备端口不能为空")
    @Min(value = 1, message = "设备端口最小为 1")
    @Max(value = 65535, message = "设备端口最大为 65535")
    private Integer port;

    @Schema(description = "主码流 URI；创建时必填，修改时留空表示不修改", example = "/Streaming/Channels/101")
    @Size(max = 4096, message = "主码流 URI 不能超过 4096 个字符")
    @ToString.Exclude
    private String mainStreamUri;

    @Schema(description = "子码流 URI；修改时留空表示不修改", example = "/Streaming/Channels/102")
    @Size(max = 4096, message = "子码流 URI 不能超过 4096 个字符")
    @ToString.Exclude
    private String subStreamUri;

    @Schema(description = "访问用户名；修改时留空表示不修改")
    @Size(max = 512, message = "用户名不能超过 512 个字符")
    @ToString.Exclude
    private String username;

    @Schema(description = "访问密码；修改时留空表示不修改")
    @Size(max = 512, message = "密码不能超过 512 个字符")
    @ToString.Exclude
    private String password;

    @Schema(description = "状态", requiredMode = Schema.RequiredMode.REQUIRED, example = "0")
    @NotNull(message = "状态不能为空")
    @InEnum(value = CommonStatusEnum.class, message = "状态必须是 {value}")
    private Integer status;

}
