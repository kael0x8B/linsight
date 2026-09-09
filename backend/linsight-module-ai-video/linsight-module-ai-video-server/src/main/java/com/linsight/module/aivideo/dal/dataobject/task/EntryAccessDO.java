package com.linsight.module.aivideo.dal.dataobject.task;
import com.baomidou.mybatisplus.annotation.TableName;
import com.baomidou.mybatisplus.annotation.TableId;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;
@Data @EqualsAndHashCode(callSuper=true) @TableName("ai_entry_access")
public class EntryAccessDO extends TenantBaseDO {
    @TableId private Long id;
    private String name;
    private Long cameraId;
    private Long nodeId;
    private Long libraryId;
    private Long modelVersionId;
    private String parameters;
    private Boolean enabled;
    private Integer version;
}
