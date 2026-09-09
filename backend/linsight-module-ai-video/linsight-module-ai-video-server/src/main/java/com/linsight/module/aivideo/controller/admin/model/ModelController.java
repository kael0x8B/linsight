package com.linsight.module.aivideo.controller.admin.model;

import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.framework.common.pojo.PageResult;
import com.linsight.module.aivideo.controller.admin.model.vo.ModelPageReqVO;
import com.linsight.module.aivideo.controller.admin.model.vo.ModelDeployReqVO;
import com.linsight.module.aivideo.controller.admin.model.vo.ModelDeploymentRespVO;
import com.linsight.module.aivideo.controller.admin.model.vo.ModelCapabilityRespVO;
import com.linsight.module.aivideo.controller.admin.model.vo.ModelRespVO;
import com.linsight.module.aivideo.controller.admin.model.vo.ModelSaveReqVO;
import com.linsight.module.aivideo.controller.admin.model.vo.ModelVersionRespVO;
import com.linsight.module.aivideo.controller.admin.model.vo.ModelVersionUploadReqVO;
import com.linsight.module.aivideo.controller.admin.model.vo.ModelTestCreateReqVO;
import com.linsight.module.aivideo.controller.admin.model.vo.ModelTestRespVO;
import com.linsight.module.aivideo.convert.model.ModelConvert;
import com.linsight.module.aivideo.service.algorithm.AlgorithmCapabilityDTO;
import com.linsight.module.aivideo.service.algorithm.AlgorithmService;
import com.linsight.module.aivideo.service.model.ModelService;
import com.linsight.module.aivideo.service.model.ModelExecutionService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.annotation.Resource;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.io.IOException;
import java.util.Collection;
import java.util.List;
import java.util.Map;

import static com.linsight.framework.common.pojo.CommonResult.success;

@Tag(name = "管理后台 - 模型资产")
@RestController
@RequestMapping("/ai-video/model")
@Validated
public class ModelController {

    @Resource
    private ModelService modelService;
    @Resource
    private ModelExecutionService modelExecutionService;
    @Resource
    private AlgorithmService algorithmService;

    @PostMapping("/create")
    @Operation(summary = "创建模型资产")
    @PreAuthorize("@ss.hasPermission('ai-video:model:create')")
    public CommonResult<Long> createModel(@Valid @RequestBody ModelSaveReqVO reqVO) {
        return success(modelService.createModel(reqVO));
    }

    @PutMapping("/update")
    @Operation(summary = "修改模型资产元数据")
    @PreAuthorize("@ss.hasPermission('ai-video:model:update')")
    public CommonResult<Boolean> updateModel(@Valid @RequestBody ModelSaveReqVO reqVO) {
        modelService.updateModel(reqVO);
        return success(true);
    }

    @DeleteMapping("/delete")
    @Operation(summary = "删除没有版本的模型资产")
    @PreAuthorize("@ss.hasPermission('ai-video:model:delete')")
    public CommonResult<Boolean> deleteModel(@RequestParam("id") Long id) {
        modelService.deleteModel(id);
        return success(true);
    }

    @GetMapping("/get")
    @Operation(summary = "获取模型资产")
    @PreAuthorize("@ss.hasPermission('ai-video:model:query')")
    public CommonResult<ModelRespVO> getModel(@RequestParam("id") Long id) {
        ModelRespVO response = ModelConvert.convert(modelService.getModel(id));
        fillCapabilities(List.of(response));
        return success(response);
    }

    @GetMapping("/page")
    @Operation(summary = "获取模型资产分页")
    @PreAuthorize("@ss.hasPermission('ai-video:model:query')")
    public CommonResult<PageResult<ModelRespVO>> getModelPage(@Valid ModelPageReqVO reqVO) {
        var page = modelService.getModelPage(reqVO);
        var versions = modelService.getVersionList(
                page.getList().stream().map(model -> model.getId()).toList());
        var summaryVersionIds = ModelConvert.collectSummaryVersionIds(page, versions);
        var deployments = modelExecutionService.getDeployments(summaryVersionIds);
        PageResult<ModelRespVO> result = ModelConvert.convertPage(page, versions, deployments);
        fillCapabilities(result.getList());
        return success(result);
    }

    private void fillCapabilities(Collection<ModelRespVO> models) {
        if (models.isEmpty()) {
            return;
        }
        Map<Long, List<AlgorithmCapabilityDTO>> capabilitiesByModelId = algorithmService.getModelCapabilities();
        for (ModelRespVO model : models) {
            model.setCapabilities(capabilitiesByModelId.getOrDefault(model.getId(), List.of()).stream()
                    .map(ModelController::toCapabilityResponse)
                    .toList());
        }
    }

    private static ModelCapabilityRespVO toCapabilityResponse(AlgorithmCapabilityDTO source) {
        ModelCapabilityRespVO response = new ModelCapabilityRespVO();
        response.setAlgorithmId(source.getAlgorithmId());
        response.setName(source.getName());
        response.setCode(source.getCode());
        response.setCapabilityKey(source.getCapabilityKey());
        response.setSceneGroup(source.getSceneGroup());
        response.setAcceptanceStatus(source.getAcceptanceStatus());
        return response;
    }

    @PostMapping(value = "/version/upload", consumes = "multipart/form-data")
    @Operation(summary = "上传不可变模型版本", description = "控制面计算 SHA256、验证格式并将文件写入对象存储")
    @PreAuthorize("@ss.hasPermission('ai-video:model:upload')")
    public CommonResult<Long> uploadVersion(@Valid ModelVersionUploadReqVO reqVO) throws IOException {
        return success(modelService.uploadVersion(reqVO));
    }

    @GetMapping("/version/list")
    @Operation(summary = "获取模型版本列表")
    @PreAuthorize("@ss.hasPermission('ai-video:model:query')")
    public CommonResult<List<ModelVersionRespVO>> getVersionList(@RequestParam("modelId") Long modelId) {
        return success(ModelConvert.convertVersions(modelService.getVersionList(modelId)));
    }

    @PostMapping("/version/publish")
    @Operation(summary = "发布或回滚模型目录版本",
            description = "只建立资产目录默认版本；单图测试、标准化输出与节点 ready 由 Story 6 完成后才能标记生产可用")
    @PreAuthorize("@ss.hasPermission('ai-video:model:publish')")
    public CommonResult<Boolean> publishVersion(@RequestParam("id") Long id) {
        modelService.publishVersion(id);
        return success(true);
    }

    @PostMapping("/deployment/create")
    @Operation(summary = "向在线节点下发幂等模型部署命令")
    @PreAuthorize("@ss.hasPermission('ai-video:model:deploy')")
    public CommonResult<Long> deploy(@Valid @RequestBody ModelDeployReqVO reqVO) {
        return success(modelExecutionService.deployModel(reqVO.getModelVersionId(), reqVO.getNodeId()));
    }

    @PostMapping("/deployment/uninstall")
    @Operation(summary = "卸载网关模型，执行端拒绝卸载使用中的模型")
    @PreAuthorize("@ss.hasPermission('ai-video:model:deploy')")
    public CommonResult<Long> uninstall(@Valid @RequestBody ModelDeployReqVO reqVO) {
        return success(modelExecutionService.uninstallModel(reqVO.getModelVersionId(), reqVO.getNodeId()));
    }

    @GetMapping("/deployment/node-list")
    @Operation(summary = "获取网关上的模型部署记录")
    @PreAuthorize("@ss.hasPermission('ai-video:model:query')")
    public CommonResult<List<ModelDeploymentRespVO>> getNodeDeployments(@RequestParam("nodeId") Long nodeId) {
        var rows = ModelConvert.convertDeployments(modelExecutionService.getNodeDeployments(nodeId));
        var names = modelService.getVersionDisplayNames(rows.stream().map(ModelDeploymentRespVO::getModelVersionId).toList());
        for (var row : rows) {
            var name = names.get(row.getModelVersionId());
            if (name != null) { row.setModelName(name.get("name")); row.setModelVersion(name.get("version")); }
        }
        return success(rows);
    }

    @GetMapping("/deployment/list")
    @Operation(summary = "获取模型版本的节点部署状态")
    @PreAuthorize("@ss.hasPermission('ai-video:model:query')")
    public CommonResult<List<ModelDeploymentRespVO>> getDeployments(
            @RequestParam("modelVersionId") Long modelVersionId) {
        return success(ModelConvert.convertDeployments(modelExecutionService.getDeployments(modelVersionId)));
    }

    @PostMapping(value = "/test/create", consumes = "multipart/form-data")
    @Operation(summary = "创建异步单图模型测试")
    @PreAuthorize("@ss.hasPermission('ai-video:model:test')")
    public CommonResult<Long> createTest(@Valid ModelTestCreateReqVO reqVO) throws IOException {
        return success(modelExecutionService.createTest(reqVO));
    }

    @GetMapping("/test/get")
    @Operation(summary = "获取单图测试结果")
    @PreAuthorize("@ss.hasPermission('ai-video:model:query')")
    public CommonResult<ModelTestRespVO> getTest(@RequestParam("id") Long id) {
        return success(ModelConvert.convertTest(modelExecutionService.getTest(id)));
    }

    @GetMapping("/test/list")
    @Operation(summary = "获取模型版本单图测试记录")
    @PreAuthorize("@ss.hasPermission('ai-video:model:query')")
    public CommonResult<List<ModelTestRespVO>> getTests(@RequestParam("modelVersionId") Long modelVersionId) {
        return success(ModelConvert.convertTests(modelExecutionService.getTests(modelVersionId)));
    }
}
