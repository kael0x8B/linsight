package com.linsight.module.aivideo.controller.admin.task;
import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.module.aivideo.controller.admin.task.vo.FaceVerificationCreateReqVO;
import com.linsight.module.aivideo.controller.admin.task.vo.FaceVerificationRespVO;
import com.linsight.module.aivideo.service.task.FaceVerificationService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.annotation.Resource;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;
import java.io.IOException;
import static com.linsight.framework.common.pojo.CommonResult.success;
@RestController @Validated @RequestMapping("/ai-video/task/face-verification")
@Tag(name="管理后台 - 主动刷脸开发验证")
public class FaceVerificationController {
    @Resource private FaceVerificationService service;
    @PostMapping("/create") @Operation(summary="本人主动发起一次开发核验")
    @PreAuthorize("@ss.hasPermission('ai-video:model:test') and @ss.hasPermission('ai-video:camera:query')")
    public CommonResult<Long> create(@Valid FaceVerificationCreateReqVO request) throws IOException {
        return success(service.create(request));
    }
    @GetMapping("/get") @Operation(summary="查询开发核验结果")
    @PreAuthorize("@ss.hasPermission('ai-video:model:test') and @ss.hasPermission('ai-video:camera:query')")
    public CommonResult<FaceVerificationRespVO> get(@RequestParam Long id) { return success(service.get(id)); }
}
