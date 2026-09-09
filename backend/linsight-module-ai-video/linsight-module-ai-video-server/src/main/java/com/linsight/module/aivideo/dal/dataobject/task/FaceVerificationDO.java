package com.linsight.module.aivideo.dal.dataobject.task;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;
import java.time.LocalDateTime;
@Data @EqualsAndHashCode(callSuper = true) @TableName("ai_face_verification")
public class FaceVerificationDO extends TenantBaseDO {
    @TableId private Long id;
    private Long cameraId;
    private Long nodeId;
    private Long modelVersionId;
    private String commandId;
    private String referenceRef;
    private String referenceSha256;
    private String parameters;
    private String status;
    private String result;
    private LocalDateTime expiresTime;
}
