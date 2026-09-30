package com.linsight.module.aivideo.controller.admin.camera.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Builder;
import lombok.Data;
import java.time.LocalDateTime;
import java.util.List;
import com.linsight.module.aivideo.service.rule.RuleRegionGeometryDTO;

@Data
@Builder
@Schema(description = "摄像头实际关联的识别任务与运行状态，不代表算法目录中所有可选能力")
public class CameraCapabilityRespVO {
    private String errorCode;
    private String errorMessage;
    private Long taskId;
    private Long entryAccessId;
    private String stationState;
    private String taskName;
    private Long algorithmId;
    private String algorithmName;
    private String capabilityKey;
    private Long nodeId;
    private String nodeName;
    private String actualStatus;
    private String desiredStatus;
    @Schema(description = "有效状态；STALE 表示运行心跳过期，OFFLINE 表示节点不可用")
    private String effectiveStatus;
    private String activeRunId;
    private LocalDateTime lastHeartbeatTime;
    private boolean validationOnly;
    private Double sampleFps;
    private String executionBackend;
    private Double analysisFps;
    private Double totalLatencyMillis;
    @Schema(description = "网关已应用的识别区域，仅含归一化顶点；未知或尚未应用时为空")
    private List<RuleRegionGeometryDTO> regions;
}
