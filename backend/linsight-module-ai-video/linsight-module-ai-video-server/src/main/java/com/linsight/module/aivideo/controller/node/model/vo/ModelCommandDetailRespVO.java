package com.linsight.module.aivideo.controller.node.model.vo;

import lombok.Data;
import java.util.Map;

@Data
public class ModelCommandDetailRespVO {
    private String commandId;
    private String commandType;
    private Integer configVersion;
    private Long modelVersionId;
    private String modelName;
    private String modelVersion;
    private String artifactUrl;
    private String artifactName;
    private String artifactFormat;
    private Boolean trustedArtifact;
    private String sha256;
    /** 新节点优先使用声明式契约；adapter 仅保留为空的兼容字段。 */
    private Map<String, Object> runtimeManifest;
    private String adapter;
    private String imageUrl;
    private String imageName;
    private Map<String, Object> parameters;
}
