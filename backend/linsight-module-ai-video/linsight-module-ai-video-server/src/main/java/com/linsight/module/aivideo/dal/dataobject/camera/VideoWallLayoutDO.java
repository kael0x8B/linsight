package com.linsight.module.aivideo.dal.dataobject.camera;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;

@TableName("ai_video_wall_layout")
@Data
@EqualsAndHashCode(callSuper = true)
public class VideoWallLayoutDO extends TenantBaseDO {

    @TableId
    private Long id;
    private Long userId;
    private Integer slotIndex;
    private String name;
    private Integer splitCount;
    private Long nodeId;
    private String schemaVersion;
    private String cameraIdsJson;
    private Boolean active;

}
