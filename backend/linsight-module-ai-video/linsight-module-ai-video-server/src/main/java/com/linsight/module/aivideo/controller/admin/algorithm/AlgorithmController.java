package com.linsight.module.aivideo.controller.admin.algorithm;

import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.framework.common.pojo.PageResult;
import com.linsight.module.aivideo.controller.admin.algorithm.vo.*;
import com.linsight.module.aivideo.convert.algorithm.AlgorithmConvert;
import com.linsight.module.aivideo.service.algorithm.AlgorithmService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.annotation.Resource;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

import static com.linsight.framework.common.pojo.CommonResult.success;

@Tag(name = "管理后台 - AI 视频算法与 Pipeline")
@RestController
@RequestMapping("/ai-video/algorithm")
@Validated
public class AlgorithmController {
    @Resource private AlgorithmService algorithmService;

    @GetMapping("/page")
    @Operation(summary = "获得算法分页")
    @PreAuthorize("@ss.hasPermission('ai-video:algorithm:query')")
    public CommonResult<PageResult<AlgorithmRespVO>> page(@Valid AlgorithmPageReqVO reqVO) {
        var algorithms = algorithmService.getAlgorithmPage(reqVO);
        PageResult<AlgorithmRespVO> page = AlgorithmConvert.convertPage(algorithms);
        fillAcceptanceStatuses(page.getList(),
                algorithmService.getPipelineAcceptanceStatuses(algorithms.getList()));
        return success(page);
    }

    @GetMapping("/get")
    @Operation(summary = "获得算法详情")
    @PreAuthorize("@ss.hasPermission('ai-video:algorithm:query')")
    public CommonResult<AlgorithmRespVO> get(@RequestParam Long id) {
        AlgorithmRespVO result = AlgorithmConvert.convert(algorithmService.getAlgorithm(id));
        fillAcceptanceStatus(result);
        return success(result);
    }

    @GetMapping("/simple-list")
    @Operation(summary = "获得可运行算法列表")
    @PreAuthorize("@ss.hasPermission('ai-video:algorithm:query')")
    public CommonResult<List<AlgorithmRespVO>> simpleList() {
        var algorithms = algorithmService.getRunnableAlgorithms();
        List<AlgorithmRespVO> result = algorithms.stream()
                .map(AlgorithmConvert::convert).toList();
        fillAcceptanceStatuses(result, algorithmService.getPipelineAcceptanceStatuses(algorithms));
        return success(result);
    }

    @PostMapping("/create")
    @Operation(summary = "创建算法")
    @PreAuthorize("@ss.hasPermission('ai-video:algorithm:create')")
    public CommonResult<Long> create(@Valid @RequestBody AlgorithmSaveReqVO reqVO) {
        return success(algorithmService.createAlgorithm(reqVO));
    }

    @PutMapping("/update")
    @Operation(summary = "更新算法，稳定编码不可修改")
    @PreAuthorize("@ss.hasPermission('ai-video:algorithm:update')")
    public CommonResult<Boolean> update(@Valid @RequestBody AlgorithmSaveReqVO reqVO) {
        algorithmService.updateAlgorithm(reqVO);
        return success(true);
    }

    @GetMapping("/pipeline/list")
    @Operation(summary = "获得 Pipeline 版本")
    @PreAuthorize("@ss.hasPermission('ai-video:algorithm:query')")
    public CommonResult<List<PipelineVersionRespVO>> pipelineList(@RequestParam Long algorithmId) {
        return success(AlgorithmConvert.convertPipelines(algorithmService.getPipelineVersions(algorithmId)));
    }

    @PostMapping("/pipeline/save")
    @Operation(summary = "保存新的不可变 Pipeline 草稿")
    @PreAuthorize("@ss.hasPermission('ai-video:algorithm:update')")
    public CommonResult<Long> savePipeline(@Valid @RequestBody PipelineSaveReqVO reqVO) {
        return success(algorithmService.savePipeline(reqVO));
    }

    @PostMapping("/pipeline/validate")
    @Operation(summary = "校验 Pipeline DAG")
    @PreAuthorize("@ss.hasPermission('ai-video:algorithm:update')")
    public CommonResult<List<String>> validatePipeline(@RequestParam Long id) {
        return success(algorithmService.validatePipeline(id));
    }

    @PostMapping("/pipeline/publish")
    @Operation(summary = "发布 Pipeline 版本")
    @PreAuthorize("@ss.hasPermission('ai-video:algorithm:publish')")
    public CommonResult<Boolean> publishPipeline(@RequestParam Long id) {
        algorithmService.publishPipeline(id);
        return success(true);
    }

    private void fillAcceptanceStatus(AlgorithmRespVO algorithm) {
        algorithm.setPipelineAcceptanceStatus(algorithmService.getPipelineAcceptanceStatus(algorithm.getId()));
    }

    private static void fillAcceptanceStatuses(List<AlgorithmRespVO> algorithms, Map<Long, String> statuses) {
        algorithms.forEach(algorithm -> algorithm.setPipelineAcceptanceStatus(statuses.get(algorithm.getId())));
    }
}
