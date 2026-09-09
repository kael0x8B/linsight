package com.linsight.module.aivideo.dal.dataobject.algorithm;
import com.baomidou.mybatisplus.annotation.TableName;
import com.baomidou.mybatisplus.annotation.TableId;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;
@Data @EqualsAndHashCode(callSuper=true) @TableName("ai_face_reference")
public class FaceReferenceDO extends TenantBaseDO {
    @TableId private Long id;
    private Long entryId;
    private Long libraryId;
    private Long modelVersionId;
    private String objectRef;
    private String sha256;
    private String validationStatus;
    private String validationCommandId;
    private java.time.LocalDateTime validUntil;
}
