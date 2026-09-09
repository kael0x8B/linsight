package com.linsight.module.aivideo.dal.dataobject.task;
import com.baomidou.mybatisplus.annotation.TableName;
import com.baomidou.mybatisplus.annotation.TableId;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;
@Data @EqualsAndHashCode(callSuper=true) @TableName("ai_entry_scan")
public class EntryScanDO extends TenantBaseDO {
    @TableId private Long id;
    private Long entryAccessId;
    private Long referenceId;
    private Long cameraId;
    private Long nodeId;
    private Long modelVersionId;
    private String commandId;
    private String mode;
    private String status;
    private String snapshot;
    private String result;
    private Long eventId;
    private java.time.LocalDateTime expiresTime;
}
