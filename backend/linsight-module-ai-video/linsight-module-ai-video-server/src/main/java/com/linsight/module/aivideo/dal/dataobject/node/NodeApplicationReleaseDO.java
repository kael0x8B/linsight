package com.linsight.module.aivideo.dal.dataobject.node;

import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;
import java.time.LocalDateTime;

@Data
@EqualsAndHashCode(callSuper = true)
@TableName("ai_node_application_release")
public class NodeApplicationReleaseDO extends TenantBaseDO {
    @TableId private Long id;
    private String requestId;
    private String profileId;
    private String profileLabel;
    private String profileDigest;
    private String architecture;
    private String devices;
    private String keyId;
    private String version;
    private String notes;
    private String status;
    private String message;
    private String executorOwner;
    private LocalDateTime leaseUntil;
    private Integer attempt;
    private Long bundleFileId;
    private Long bootstrapFileId;
    private Long publicKeyFileId;
    private String fileName;
    private Long size;
    private String sha256;
    private String bootstrapSha256;
    private String sourceSha256;
    private LocalDateTime finishTime;
}
