package com.linsight.module.aivideo.controller.admin.model.vo;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;
import lombok.Data;
import org.springframework.web.multipart.MultipartFile;

@Data
public class ModelVersionUploadReqVO {

    @NotNull(message = "模型编号不能为空")
    private Long modelId;
    @NotBlank(message = "版本标识不能为空")
    @Size(max = 64)
    private String version;
    @Size(max = 500)
    private String sourceRepository;
    @Size(max = 128)
    private String sourceRevision;
    @NotBlank(message = "许可证或权重使用条款说明不能为空")
    @Size(max = 128)
    private String licenseSpdx;
    /** 声明式 Runtime 执行契约。允许草稿暂缺，但发布与部署前必须存在。 */
    @Size(max = 65535)
    private String runtimeManifest;
    @NotNull(message = "模型文件不能为空")
    private MultipartFile file;

}
