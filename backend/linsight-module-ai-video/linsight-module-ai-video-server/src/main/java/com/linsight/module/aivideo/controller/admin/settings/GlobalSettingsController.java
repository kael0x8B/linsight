package com.linsight.module.aivideo.controller.admin.settings;

import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.module.aivideo.controller.admin.settings.vo.GlobalSettingsRespVO;
import com.linsight.module.aivideo.controller.admin.settings.vo.GlobalSettingsSaveReqVO;
import com.linsight.module.aivideo.controller.admin.settings.vo.GlobalSettingsVersionRespVO;
import com.linsight.module.aivideo.service.settings.GlobalSettingsService;
import com.linsight.framework.security.core.service.SecurityFrameworkService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.annotation.Resource;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

import static com.linsight.framework.common.pojo.CommonResult.success;

@Tag(name = "管理后台 - AI 视频全局参数")
@RestController
@RequestMapping("/ai-video/settings")
@Validated
public class GlobalSettingsController {
    @Resource private GlobalSettingsService globalSettingsService;
    @Resource private SecurityFrameworkService securityFrameworkService;

    @GetMapping("/get")
    @Operation(summary = "获取当前强类型 AI 全局参数")
    @PreAuthorize("@ss.hasPermission('ai-video:settings:query')")
    public CommonResult<GlobalSettingsRespVO> get() {
        return success(globalSettingsService.getCurrent());
    }

    @PostMapping("/save")
    @Operation(summary = "保存全局参数并生成不可变版本")
    @PreAuthorize("@ss.hasPermission('ai-video:settings:update')")
    public CommonResult<GlobalSettingsVersionRespVO> save(
            @Valid @RequestBody GlobalSettingsSaveReqVO reqVO) {
        if (!"NEW_TASKS".equals(reqVO.getApplyScope())
                && !securityFrameworkService.hasPermission("ai-video:settings:deploy")) {
            throw new AccessDeniedException("Missing ai-video:settings:deploy permission");
        }
        return success(globalSettingsService.save(reqVO));
    }

    @GetMapping("/version/list")
    @Operation(summary = "获取最近 50 个参数版本")
    @PreAuthorize("@ss.hasPermission('ai-video:settings:query')")
    public CommonResult<List<GlobalSettingsVersionRespVO>> getVersions() {
        return success(globalSettingsService.getVersions());
    }
}
