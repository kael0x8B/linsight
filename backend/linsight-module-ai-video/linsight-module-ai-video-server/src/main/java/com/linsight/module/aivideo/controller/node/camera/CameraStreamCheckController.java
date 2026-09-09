package com.linsight.module.aivideo.controller.node.camera;

import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.module.aivideo.controller.node.camera.vo.StreamCheckReportReqVO;
import com.linsight.module.aivideo.controller.node.camera.vo.StreamCheckTaskRespVO;
import com.linsight.module.aivideo.service.camera.StreamCheckService;
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

@Tag(name = "节点端 - 摄像头检测")
@RestController
@RequestMapping("/ai-video/camera/check")
@Validated
public class CameraStreamCheckController {

    @Resource
    private StreamCheckService streamCheckService;

    @PostMapping("/pull")
    @Operation(summary = "领取一个待执行的摄像头检测任务")
    public CommonResult<StreamCheckTaskRespVO> pull(Authentication authentication) {
        return success(streamCheckService.claimStreamCheck((Long) authentication.getPrincipal()));
    }

    @PostMapping("/report")
    @Operation(summary = "上报摄像头检测结果")
    public CommonResult<Boolean> report(@Valid @RequestBody StreamCheckReportReqVO reqVO,
                                        Authentication authentication) {
        streamCheckService.reportStreamCheck((Long) authentication.getPrincipal(), reqVO);
        return success(true);
    }

}
