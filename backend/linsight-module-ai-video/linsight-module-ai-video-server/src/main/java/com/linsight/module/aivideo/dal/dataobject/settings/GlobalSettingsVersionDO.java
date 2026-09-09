package com.linsight.module.aivideo.dal.dataobject.settings;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;

import java.time.LocalDateTime;

@TableName("ai_global_settings_version")
@Data
@EqualsAndHashCode(callSuper = true)
public class GlobalSettingsVersionDO extends TenantBaseDO {
    @TableId private Long id;
    private Integer versionNo;
    private String schemaVersion;
    private String settingsJson;
    private String diffJson;
    private String applyScope;
    private String grayTaskIdsJson;
    private String status;
    private Integer affectedTaskCount;
    private Integer commandCount;
    private LocalDateTime appliedAt;
}
