package com.linsight.module.aivideo.controller.node.camera;

import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.module.aivideo.controller.node.camera.vo.NodeOverlayReportReqVO;
import com.linsight.module.aivideo.service.camera.PreviewService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.annotation.Resource;
import jakarta.validation.Valid;
import org.springframework.security.core.Authentication;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static com.linsight.framework.common.pojo.CommonResult.success;

@Tag(name = "节点端 - 实时检测框")
@RestController
@RequestMapping("/ai-video/camera/overlay")
@Validated
public class CameraOverlayController {

    @Resource
    private PreviewService previewService;

    @PostMapping("/report")
    @com.linsight.framework.apilog.core.annotation.ApiAccessLog(enable = false, requestEnable = false)
    @Operation(summary = "向当前摄像头的活动预览会话上报最新检测框")
    public CommonResult<Boolean> report(@Valid @RequestBody NodeOverlayReportReqVO reqVO,
                                        Authentication authentication) {
        previewService.publishOverlay(reqVO, (Long) authentication.getPrincipal());
        return success(true);
    }
}
