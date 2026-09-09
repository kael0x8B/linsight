package com.linsight.module.aivideo.service.task;

import java.util.List;

public interface TaskSettingsService {
    ApplyResult apply(Integer versionNo, String settingsJson, String scope, List<Long> grayTaskIds);

    record ApplyResult(int affectedTaskCount, int commandCount) { }
}
