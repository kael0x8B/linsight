package com.linsight.module.aivideo.controller.node.model;

import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.module.aivideo.controller.node.model.vo.ModelCommandDetailRespVO;
import com.linsight.module.aivideo.service.model.ModelExecutionService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.annotation.Resource;
import org.springframework.security.core.Authentication;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import static com.linsight.framework.common.pojo.CommonResult.success;

@Tag(name = "节点端 - 模型命令详情")
@RestController
@RequestMapping("/ai-video/model/command")
@Validated
public class ModelNodeController {
    @Resource private ModelExecutionService modelExecutionService;

    @GetMapping("/get")
    @Operation(summary = "获取当前节点模型命令的短时下载地址和参数")
    public CommonResult<ModelCommandDetailRespVO> get(@RequestParam("commandId") String commandId,
                                                       Authentication authentication) {
        return success(modelExecutionService.getCommandDetail(commandId,
                (Long) authentication.getPrincipal()));
    }
}
