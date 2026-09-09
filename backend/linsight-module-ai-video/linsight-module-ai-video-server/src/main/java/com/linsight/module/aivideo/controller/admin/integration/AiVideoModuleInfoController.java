package com.linsight.module.aivideo.controller.admin.integration;

import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.module.aivideo.controller.admin.integration.vo.AiVideoModuleInfoRespVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static com.linsight.framework.common.pojo.CommonResult.success;
import static com.linsight.module.aivideo.api.AiVideoApiConstants.CONTRACT_VERSION;

@Tag(name = "管理后台 - AI 视频平台能力")
@RestController
@RequestMapping("/ai-video/integration")
@Validated
public class AiVideoModuleInfoController {

    @GetMapping("/module-info")
    @Operation(summary = "查询 AI 视频模块契约信息")
    @PreAuthorize("@ss.hasPermission('ai-video:integration:query')")
    public CommonResult<AiVideoModuleInfoRespVO> getModuleInfo() {
        return success(new AiVideoModuleInfoRespVO("linsight-module-ai-video", CONTRACT_VERSION,
                "java-control-plane"));
    }

}
