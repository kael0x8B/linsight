package com.linsight.module.aivideo.service.settings;

import com.fasterxml.jackson.core.type.TypeReference;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.module.aivideo.controller.admin.settings.vo.AiGlobalSettingsVO;
import com.linsight.module.aivideo.controller.admin.settings.vo.GlobalSettingsRespVO;
import com.linsight.module.aivideo.controller.admin.settings.vo.GlobalSettingsSaveReqVO;
import com.linsight.module.aivideo.controller.admin.settings.vo.GlobalSettingsVersionRespVO;
import com.linsight.module.aivideo.dal.dataobject.settings.GlobalSettingsVersionDO;
import com.linsight.module.aivideo.dal.mysql.settings.GlobalSettingsVersionMapper;
import com.linsight.module.aivideo.service.task.TaskSettingsService;
import com.linsight.module.infra.api.config.ConfigApi;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

import static com.linsight.framework.common.exception.util.ServiceExceptionUtil.exception;
import static com.linsight.module.aivideo.enums.settings.ErrorCodeConstants.SETTINGS_GRAY_TASKS_REQUIRED;
import static com.linsight.module.aivideo.enums.settings.ErrorCodeConstants.SETTINGS_VERSION_CONFLICT;

@Service
public class GlobalSettingsServiceImpl implements GlobalSettingsService {
    static final String DEFAULT_CONFIG_KEY = "linsight.ai-video.settings.defaults";
    static final String FALLBACK_DEFAULTS = """
            {"schemaVersion":"1.0","recordBeforeSeconds":10,"recordAfterSeconds":20,
             "defaultConfidence":0.5,"defaultFps":1.0,"evidenceStorageMode":"OBJECT_STORAGE",
             "evidenceRetentionDays":30,"notificationsEnabled":true,"nodeOfflineThresholdSeconds":60}
            """;
    private static final TypeReference<List<Long>> LONG_LIST = new TypeReference<>() { };

    @Resource private GlobalSettingsVersionMapper versionMapper;
    @Resource private TaskSettingsService taskSettingsService;
    @Resource private ConfigApi configApi;

    @Override
    public GlobalSettingsRespVO getCurrent() {
        GlobalSettingsVersionDO latest = versionMapper.selectLatest();
        if (latest == null) return new GlobalSettingsRespVO(0, readDefaults());
        return new GlobalSettingsRespVO(latest.getVersionNo(), parseSettings(latest.getSettingsJson()));
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public GlobalSettingsVersionRespVO save(GlobalSettingsSaveReqVO reqVO) {
        GlobalSettingsVersionDO latest = versionMapper.selectLatest();
        int currentVersion = latest == null ? 0 : latest.getVersionNo();
        if (!Objects.equals(reqVO.getExpectedVersionNo(), currentVersion)) {
            throw exception(SETTINGS_VERSION_CONFLICT);
        }
        if ("GRAY".equals(reqVO.getApplyScope())
                && (reqVO.getGrayTaskIds() == null || reqVO.getGrayTaskIds().isEmpty())) {
            throw exception(SETTINGS_GRAY_TASKS_REQUIRED);
        }
        AiGlobalSettingsVO previous = latest == null ? readDefaults() : parseSettings(latest.getSettingsJson());
        String settingsJson = JsonUtils.toJsonString(reqVO.getSettings());
        Map<String, Object> diff = diff(previous, reqVO.getSettings());
        int versionNo = currentVersion + 1;
        TaskSettingsService.ApplyResult applied = taskSettingsService.apply(versionNo, settingsJson,
                reqVO.getApplyScope(), reqVO.getGrayTaskIds());

        GlobalSettingsVersionDO value = new GlobalSettingsVersionDO();
        value.setVersionNo(versionNo);
        value.setSchemaVersion(reqVO.getSettings().getSchemaVersion());
        value.setSettingsJson(settingsJson);
        value.setDiffJson(JsonUtils.toJsonString(diff));
        value.setApplyScope(reqVO.getApplyScope());
        value.setGrayTaskIdsJson(JsonUtils.toJsonString(reqVO.getGrayTaskIds() == null
                ? List.of() : reqVO.getGrayTaskIds()));
        value.setAffectedTaskCount(applied.affectedTaskCount());
        value.setCommandCount(applied.commandCount());
        value.setStatus(applied.affectedTaskCount() == 0 ? "APPLIED"
                : applied.affectedTaskCount() == applied.commandCount() ? "DISPATCHED" : "PARTIAL");
        value.setAppliedAt(LocalDateTime.now());
        versionMapper.insert(value);
        return toResponse(value);
    }

    @Override
    public List<GlobalSettingsVersionRespVO> getVersions() {
        return versionMapper.selectRecent().stream().map(this::toResponse).toList();
    }

    private AiGlobalSettingsVO readDefaults() {
        try {
            String configured = configApi.getConfigValueByKey(DEFAULT_CONFIG_KEY).getCheckedData();
            return parseSettings(configured == null || configured.isBlank() ? FALLBACK_DEFAULTS : configured);
        } catch (RuntimeException ignored) {
            return parseSettings(FALLBACK_DEFAULTS);
        }
    }

    private static AiGlobalSettingsVO parseSettings(String json) {
        return JsonUtils.parseObject(json, AiGlobalSettingsVO.class);
    }

    private GlobalSettingsVersionRespVO toResponse(GlobalSettingsVersionDO value) {
        GlobalSettingsVersionRespVO result = new GlobalSettingsVersionRespVO();
        result.setId(value.getId());
        result.setVersionNo(value.getVersionNo());
        result.setSettings(parseSettings(value.getSettingsJson()));
        result.setDiff(JsonUtils.parseMap(value.getDiffJson()));
        result.setApplyScope(value.getApplyScope());
        List<Long> taskIds = JsonUtils.parseObjectQuietly(value.getGrayTaskIdsJson(), LONG_LIST);
        result.setGrayTaskIds(taskIds == null ? List.of() : taskIds);
        result.setStatus(value.getStatus());
        result.setAffectedTaskCount(value.getAffectedTaskCount());
        result.setCommandCount(value.getCommandCount());
        result.setAppliedAt(value.getAppliedAt());
        result.setCreator(value.getCreator());
        return result;
    }

    private static Map<String, Object> diff(AiGlobalSettingsVO before, AiGlobalSettingsVO after) {
        Map<String, Object> left = JsonUtils.parseMap(JsonUtils.toJsonString(before));
        Map<String, Object> right = JsonUtils.parseMap(JsonUtils.toJsonString(after));
        Map<String, Object> result = new LinkedHashMap<>();
        right.forEach((key, value) -> {
            if (!Objects.equals(left.get(key), value)) {
                result.put(key, Map.of("before", left.get(key), "after", value));
            }
        });
        return result;
    }
}
