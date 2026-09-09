package com.linsight.module.aivideo.dal.dataobject.camera;

import com.baomidou.mybatisplus.annotation.TableField;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.baomidou.mybatisplus.annotation.Version;
import com.linsight.framework.mybatis.core.type.EncryptTypeHandler;
import com.linsight.framework.tenant.core.db.TenantBaseDO;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.ToString;

import java.time.LocalDateTime;

@TableName(value = "ai_camera", autoResultMap = true)
@Data
@EqualsAndHashCode(callSuper = true)
public class CameraDO extends TenantBaseDO {

    @TableId
    private Long id;
    private String name;
    private String code;
    private Long groupId;
    private String protocol;
    private String host;
    private Integer port;

    @TableField(value = "main_stream_uri_ciphertext", typeHandler = EncryptTypeHandler.class)
    @ToString.Exclude
    private String mainStreamUri;
    @TableField(value = "sub_stream_uri_ciphertext", typeHandler = EncryptTypeHandler.class)
    @ToString.Exclude
    private String subStreamUri;
    @TableField(value = "username_ciphertext", typeHandler = EncryptTypeHandler.class)
    @ToString.Exclude
    private String username;
    @TableField(value = "password_ciphertext", typeHandler = EncryptTypeHandler.class)
    @ToString.Exclude
    private String password;

    private String credentialKeyVersion;
    private Integer onlineStatus;
    private LocalDateTime lastOnlineTime;
    private LocalDateTime lastCheckTime;
    private String lastErrorCode;
    private String lastErrorMessage;
    private Integer status;

    @Version
    private Integer version;

}
