package com.linsight.module.aivideo.dal.dataobject.camera;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;

@TableName("ai_camera_group")
@Data
@EqualsAndHashCode(callSuper = true)
public class CameraGroupDO extends TenantBaseDO {

    public static final Long ROOT_PARENT_ID = 0L;
    public static final String ROOT_PATH = "/";

    @TableId
    private Long id;
    private String name;
    private Long parentId;
    private String path;
    private Integer sort;
    private Integer status;

}
