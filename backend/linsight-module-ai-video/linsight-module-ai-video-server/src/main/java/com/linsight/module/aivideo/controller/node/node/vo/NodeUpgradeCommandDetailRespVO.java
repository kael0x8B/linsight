package com.linsight.module.aivideo.controller.node.node.vo;

import lombok.Data;

@Data
public class NodeUpgradeCommandDetailRespVO {
    private String commandId;
    private String commandType;
    private Integer configVersion;
    private String targetVersion;
    private String packageUrl;
    private String packageName;
    private String sha256;
    private String signature;
}
