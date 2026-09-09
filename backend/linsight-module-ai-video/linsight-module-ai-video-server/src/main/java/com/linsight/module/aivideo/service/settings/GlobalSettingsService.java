package com.linsight.module.aivideo.service.settings;

import com.linsight.module.aivideo.controller.admin.settings.vo.GlobalSettingsRespVO;
import com.linsight.module.aivideo.controller.admin.settings.vo.GlobalSettingsSaveReqVO;
import com.linsight.module.aivideo.controller.admin.settings.vo.GlobalSettingsVersionRespVO;

import java.util.List;

public interface GlobalSettingsService {
    GlobalSettingsRespVO getCurrent();
    GlobalSettingsVersionRespVO save(GlobalSettingsSaveReqVO reqVO);
    List<GlobalSettingsVersionRespVO> getVersions();
}
