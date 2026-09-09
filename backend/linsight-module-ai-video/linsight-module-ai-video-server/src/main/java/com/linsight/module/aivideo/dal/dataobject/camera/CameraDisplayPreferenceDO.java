package com.linsight.module.aivideo.dal.dataobject.camera;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;
@TableName("ai_camera_display_preference")
@Data
@EqualsAndHashCode(callSuper = true)
public class CameraDisplayPreferenceDO extends TenantBaseDO {
 @TableId private Long id;
 private Long userId;
 private Long cameraId;
 private String hiddenLayersJson;
}
