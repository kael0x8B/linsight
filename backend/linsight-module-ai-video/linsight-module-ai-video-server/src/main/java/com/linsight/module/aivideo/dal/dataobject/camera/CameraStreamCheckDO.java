package com.linsight.module.aivideo.dal.dataobject.camera;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;

import java.time.LocalDateTime;

@TableName("ai_camera_stream_check")
@Data
@EqualsAndHashCode(callSuper = true)
public class CameraStreamCheckDO extends TenantBaseDO {

    @TableId
    private Long id;
    private Long cameraId;
    private Long nodeId;
    private String status;
    private String diagnosticId;
    private String stageResults;
    private String streamInfo;
    private String errorCode;
    private String errorMessage;
    private LocalDateTime startTime;
    private LocalDateTime finishTime;

}
