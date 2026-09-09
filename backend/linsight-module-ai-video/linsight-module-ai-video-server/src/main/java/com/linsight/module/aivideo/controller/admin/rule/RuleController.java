package com.linsight.module.aivideo.controller.admin.rule;

import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.framework.common.pojo.PageResult;
import com.linsight.module.aivideo.controller.admin.rule.vo.RuleDryRunReqVO;
import com.linsight.module.aivideo.controller.admin.rule.vo.RuleDryRunRespVO;
import com.linsight.module.aivideo.controller.admin.rule.vo.RulePageReqVO;
import com.linsight.module.aivideo.controller.admin.rule.vo.RuleRespVO;
import com.linsight.module.aivideo.controller.admin.rule.vo.RuleSaveReqVO;
import com.linsight.module.aivideo.controller.admin.rule.vo.RuleVersionRespVO;
import com.linsight.module.aivideo.controller.admin.rule.vo.RuleVersionSaveReqVO;
import com.linsight.module.aivideo.convert.rule.RuleConvert;
import com.linsight.module.aivideo.service.rule.RuleService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.annotation.Resource;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

import static com.linsight.framework.common.pojo.CommonResult.success;

@Tag(name = "管理后台 - AI 视频规则")
@RestController
@RequestMapping("/ai-video/rule")
@Validated
public class RuleController {
    @Resource private RuleService ruleService;

    @PostMapping("/runtime-dry-run")
    @Operation(summary = "在节点真实规则引擎上试算检测序列，不创建任务或事件")
    @PreAuthorize("@ss.hasPermission('ai-video:rule:dry-run')")
    public CommonResult<java.util.Map<String, Object>> runtimeDryRun(@Valid @RequestBody RuleDryRunReqVO reqVO) {
        return success(ruleService.runtimeDryRun(reqVO));
    }

    @GetMapping("/page")
    @Operation(summary = "获得规则分页")
    @PreAuthorize("@ss.hasPermission('ai-video:rule:query')")
    public CommonResult<PageResult<RuleRespVO>> page(@Valid RulePageReqVO reqVO) {
        return success(RuleConvert.convertPage(ruleService.getRulePage(reqVO)));
    }

    @GetMapping("/get")
    @Operation(summary = "获得规则详情")
    @PreAuthorize("@ss.hasPermission('ai-video:rule:query')")
    public CommonResult<RuleRespVO> get(@RequestParam Long id) {
        return success(RuleConvert.convert(ruleService.getRule(id)));
    }

    @GetMapping("/simple-list")
    @Operation(summary = "获得已发布规则列表")
    @PreAuthorize("@ss.hasPermission('ai-video:rule:query')")
    public CommonResult<List<RuleRespVO>> simpleList() {
        return success(ruleService.getPublishedRules().stream().map(RuleConvert::convert).toList());
    }

    @PostMapping("/create")
    @Operation(summary = "创建规则")
    @PreAuthorize("@ss.hasPermission('ai-video:rule:create')")
    public CommonResult<Long> create(@Valid @RequestBody RuleSaveReqVO reqVO) {
        return success(ruleService.createRule(reqVO));
    }

    @PutMapping("/update")
    @Operation(summary = "更新规则元数据，稳定编码不可修改")
    @PreAuthorize("@ss.hasPermission('ai-video:rule:update')")
    public CommonResult<Boolean> update(@Valid @RequestBody RuleSaveReqVO reqVO) {
        ruleService.updateRule(reqVO);
        return success(true);
    }

    @GetMapping("/version/list")
    @Operation(summary = "获得不可变规则版本")
    @PreAuthorize("@ss.hasPermission('ai-video:rule:query')")
    public CommonResult<List<RuleVersionRespVO>> versions(@RequestParam Long ruleId) {
        return success(RuleConvert.convertVersions(ruleService.getVersions(ruleId)));
    }

    @PostMapping("/version/save")
    @Operation(summary = "保存新的不可变规则草稿")
    @PreAuthorize("@ss.hasPermission('ai-video:rule:update')")
    public CommonResult<Long> saveVersion(@Valid @RequestBody RuleVersionSaveReqVO reqVO) {
        return success(ruleService.saveVersion(reqVO));
    }

    @PostMapping("/version/validate")
    @Operation(summary = "校验 ROI、时序与组合 AST")
    @PreAuthorize("@ss.hasPermission('ai-video:rule:update')")
    public CommonResult<List<String>> validateVersion(@RequestParam Long id) {
        return success(ruleService.validateVersion(id));
    }

    @PostMapping("/version/publish")
    @Operation(summary = "发布规则版本")
    @PreAuthorize("@ss.hasPermission('ai-video:rule:publish')")
    public CommonResult<Boolean> publishVersion(@RequestParam Long id) {
        ruleService.publishVersion(id);
        return success(true);
    }

    @PostMapping("/dry-run")
    @Operation(summary = "使用离线检测序列试跑规则")
    @PreAuthorize("@ss.hasPermission('ai-video:rule:dry-run')")
    public CommonResult<RuleDryRunRespVO> dryRun(@Valid @RequestBody RuleDryRunReqVO reqVO) {
        return success(ruleService.dryRun(reqVO));
    }
}
