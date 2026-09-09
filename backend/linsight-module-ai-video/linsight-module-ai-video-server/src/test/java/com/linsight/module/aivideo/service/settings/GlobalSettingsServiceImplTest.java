package com.linsight.module.aivideo.service.settings;

import com.linsight.framework.common.exception.ServiceException;
import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.module.aivideo.controller.admin.settings.vo.AiGlobalSettingsVO;
import com.linsight.module.aivideo.controller.admin.settings.vo.GlobalSettingsSaveReqVO;
import com.linsight.module.aivideo.dal.dataobject.settings.GlobalSettingsVersionDO;
import com.linsight.module.aivideo.dal.mysql.settings.GlobalSettingsVersionMapper;
import com.linsight.module.aivideo.service.task.TaskSettingsService;
import com.linsight.module.infra.api.config.ConfigApi;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.test.util.ReflectionTestUtils;

import java.math.BigDecimal;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class GlobalSettingsServiceImplTest {
    private GlobalSettingsVersionMapper versionMapper;
    private TaskSettingsService taskSettingsService;
    private GlobalSettingsServiceImpl service;

    @BeforeEach
    void setUp() {
        versionMapper = mock(GlobalSettingsVersionMapper.class);
        taskSettingsService = mock(TaskSettingsService.class);
        ConfigApi configApi = mock(ConfigApi.class);
        when(configApi.getConfigValueByKey(any())).thenReturn(CommonResult.success(null));
        service = new GlobalSettingsServiceImpl();
        ReflectionTestUtils.setField(service, "versionMapper", versionMapper);
        ReflectionTestUtils.setField(service, "taskSettingsService", taskSettingsService);
        ReflectionTestUtils.setField(service, "configApi", configApi);
    }

    @Test
    void saveShouldPersistTypedDiffAndPartialDispatchResult() {
        when(taskSettingsService.apply(any(), any(), any(), any()))
                .thenReturn(new TaskSettingsService.ApplyResult(2, 1));
        GlobalSettingsSaveReqVO request = request();
        request.getSettings().setDefaultConfidence(new BigDecimal("0.70"));
        request.setApplyScope("ALL_RUNNING");

        var result = service.save(request);

        ArgumentCaptor<GlobalSettingsVersionDO> captor = ArgumentCaptor.forClass(GlobalSettingsVersionDO.class);
        verify(versionMapper).insert(captor.capture());
        assertThat(result.getVersionNo()).isEqualTo(1);
        assertThat(result.getStatus()).isEqualTo("PARTIAL");
        assertThat(result.getDiff()).containsKey("defaultConfidence");
        assertThat(captor.getValue().getAffectedTaskCount()).isEqualTo(2);
        assertThat(captor.getValue().getCommandCount()).isEqualTo(1);
    }

    @Test
    void staleExpectedVersionShouldBeRejected() {
        GlobalSettingsVersionDO existing = new GlobalSettingsVersionDO();
        existing.setVersionNo(3);
        when(versionMapper.selectLatest()).thenReturn(existing);

        assertThatThrownBy(() -> service.save(request())).isInstanceOf(ServiceException.class);
    }

    private static GlobalSettingsSaveReqVO request() {
        AiGlobalSettingsVO settings = new AiGlobalSettingsVO();
        settings.setSchemaVersion("1.0");
        settings.setRecordBeforeSeconds(10);
        settings.setRecordAfterSeconds(20);
        settings.setDefaultConfidence(new BigDecimal("0.50"));
        settings.setDefaultFps(new BigDecimal("1.0"));
        settings.setEvidenceStorageMode("OBJECT_STORAGE");
        settings.setEvidenceRetentionDays(30);
        settings.setNotificationsEnabled(true);
        settings.setNodeOfflineThresholdSeconds(60);
        GlobalSettingsSaveReqVO request = new GlobalSettingsSaveReqVO();
        request.setExpectedVersionNo(0);
        request.setSettings(settings);
        request.setApplyScope("NEW_TASKS");
        request.setGrayTaskIds(List.of());
        return request;
    }
}
