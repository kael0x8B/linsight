package com.linsight.module.aivideo.dal.dataobject.algorithm;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;

@TableName("ai_recognition_library_entry")
@Data
@EqualsAndHashCode(callSuper = true)
public class RecognitionLibraryEntryDO extends TenantBaseDO {
    @TableId private Long id;
    private Long libraryId;
    private String name;
    private String externalCode;
    private String mediaRef;
    private String featureStatus;
    private String attributes;
    private Integer status;
}
