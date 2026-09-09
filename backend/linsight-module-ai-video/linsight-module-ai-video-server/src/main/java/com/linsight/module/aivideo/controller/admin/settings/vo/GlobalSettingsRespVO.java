package com.linsight.module.aivideo.controller.admin.settings.vo;

import lombok.AllArgsConstructor;
import lombok.Data;

@Data
@AllArgsConstructor
public class GlobalSettingsRespVO {
    private Integer versionNo;
    private AiGlobalSettingsVO settings;
}
