package com.linsight.module.aivideo.dal.dataobject.algorithm;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;

@TableName("ai_recognition_library")
@Data
@EqualsAndHashCode(callSuper = true)
public class RecognitionLibraryDO extends TenantBaseDO {
    @TableId private Long id;
    private String name;
    private String code;
    private String libraryType;
    private String description;
    private Long engineModelVersionId;
    private Integer featureDimension;
    private String matchMode;
    private Integer status;
}
