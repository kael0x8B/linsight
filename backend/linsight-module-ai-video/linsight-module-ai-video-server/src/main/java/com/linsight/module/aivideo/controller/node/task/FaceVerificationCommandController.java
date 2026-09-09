package com.linsight.module.aivideo.controller.node.task;
import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.module.aivideo.service.task.FaceVerificationService;
import jakarta.annotation.Resource;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import java.util.Map;
import static com.linsight.framework.common.pojo.CommonResult.success;
@RestController @RequestMapping("/ai-video/task/face-verification")
public class FaceVerificationCommandController {
    @Resource private FaceVerificationService service;
    @GetMapping("/command")
    public CommonResult<Map<String,Object>> command(@RequestParam String commandId, Authentication authentication) {
        return success(service.command(commandId, (Long) authentication.getPrincipal()));
    }
}
