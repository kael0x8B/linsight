package com.linsight.module.aivideo.controller.admin.algorithm;

import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.module.aivideo.service.algorithm.AlgorithmPackageService;
import com.linsight.module.aivideo.service.algorithm.AlgorithmPackageValidator;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.annotation.Resource;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import java.io.IOException;
import java.util.List;
import java.util.Map;
import static com.linsight.framework.common.pojo.CommonResult.success;

@RestController
@RequestMapping("/ai-video/algorithm/package")
@Tag(name = "管理后台 - 可部署算法包")
@Validated
public class AlgorithmPackageController {
    @Resource private AlgorithmPackageService packageService;

    @GetMapping("/list")
    @Operation(summary = "列出算法包及不可变版本")
    @PreAuthorize("@ss.hasPermission('ai-video:algorithm:query')")
    public CommonResult<List<Map<String, Object>>> list() { return success(packageService.list()); }

    @GetMapping("/download-url")
    @Operation(summary = "下载指定算法包的原始 ZIP，地址十分钟有效")
    @PreAuthorize("@ss.hasPermission('ai-video:algorithm:query')")
    public CommonResult<String> downloadUrl(@RequestParam Long pipelineVersionId) {
        return success(packageService.downloadUrl(pipelineVersionId));
    }

    @GetMapping("/resolve")
    @Operation(summary = "解析当前网关的算法模型依赖")
    @PreAuthorize("@ss.hasPermission('ai-video:algorithm:query') and @ss.hasPermission('ai-video:model:query') and @ss.hasPermission('ai-video:node:query')")
    public CommonResult<Map<String, Object>> resolve(@RequestParam Long pipelineVersionId, @RequestParam Long nodeId) {
        return success(packageService.resolve(pipelineVersionId, nodeId));
    }

    @PostMapping("/upload")
    @Operation(summary = "上传并校验算法包，保存为待发布版本")
    @PreAuthorize("@ss.hasPermission('ai-video:algorithm:create') and @ss.hasPermission('ai-video:algorithm:update')")
    public CommonResult<Map<String, Object>> upload(@RequestParam MultipartFile file) throws IOException {
        if (file.getSize() > AlgorithmPackageValidator.MAX_BYTES) throw AlgorithmPackageValidator.invalid("算法包最大 8 MB");
        return success(packageService.upload(file.getBytes()));
    }
}
