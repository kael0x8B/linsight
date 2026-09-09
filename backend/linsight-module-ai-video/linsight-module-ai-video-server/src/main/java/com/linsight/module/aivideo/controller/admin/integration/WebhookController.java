package com.linsight.module.aivideo.controller.admin.integration;

import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.framework.common.pojo.PageResult;
import com.linsight.module.aivideo.controller.admin.integration.vo.WebhookDeliveryPageReqVO;
import com.linsight.module.aivideo.controller.admin.integration.vo.WebhookDeliveryRespVO;
import com.linsight.module.aivideo.controller.admin.integration.vo.WebhookPageReqVO;
import com.linsight.module.aivideo.controller.admin.integration.vo.WebhookRespVO;
import com.linsight.module.aivideo.controller.admin.integration.vo.WebhookSaveReqVO;
import com.linsight.module.aivideo.controller.admin.integration.vo.WebhookSecretRespVO;
import com.linsight.module.aivideo.service.integration.WebhookService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.annotation.Resource;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
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

import static com.linsight.framework.common.pojo.CommonResult.success;

@Tag(name = "管理后台 - AI 视频 Webhook 集成")
@RestController
@RequestMapping("/ai-video/webhook")
@Validated
public class WebhookController {
    @Resource private WebhookService webhookService;

    @GetMapping("/page")
    @Operation(summary = "获取 Webhook 端点分页")
    @PreAuthorize("@ss.hasPermission('ai-video:webhook:query')")
    public CommonResult<PageResult<WebhookRespVO>> getPage(@Valid WebhookPageReqVO reqVO) {
        return success(webhookService.getPage(reqVO));
    }

    @GetMapping("/get")
    @Operation(summary = "获取 Webhook 端点")
    @PreAuthorize("@ss.hasPermission('ai-video:webhook:query')")
    public CommonResult<WebhookRespVO> get(@RequestParam("id") Long id) {
        return success(webhookService.get(id));
    }

    @PostMapping("/create")
    @Operation(summary = "创建 Webhook 端点", description = "签名密钥仅在本次响应中显示")
    @PreAuthorize("@ss.hasPermission('ai-video:webhook:create')")
    public CommonResult<WebhookSecretRespVO> create(@Valid @RequestBody WebhookSaveReqVO reqVO) {
        return success(webhookService.create(reqVO));
    }

    @PutMapping("/update")
    @Operation(summary = "修改 Webhook 端点")
    @PreAuthorize("@ss.hasPermission('ai-video:webhook:update')")
    public CommonResult<Boolean> update(@Valid @RequestBody WebhookSaveReqVO reqVO) {
        webhookService.update(reqVO);
        return success(true);
    }

    @DeleteMapping("/delete")
    @Operation(summary = "删除 Webhook 端点")
    @PreAuthorize("@ss.hasPermission('ai-video:webhook:delete')")
    public CommonResult<Boolean> delete(@RequestParam("id") Long id) {
        webhookService.delete(id);
        return success(true);
    }

    @PutMapping("/update-status")
    @Operation(summary = "启用或停用 Webhook 端点")
    @PreAuthorize("@ss.hasPermission('ai-video:webhook:update-status')")
    public CommonResult<Boolean> updateStatus(@RequestParam("id") Long id,
                                               @RequestParam("status") @Min(0) @Max(1) Integer status) {
        webhookService.updateStatus(id, status);
        return success(true);
    }

    @PostMapping("/test")
    @Operation(summary = "创建 Webhook 模拟事件测试")
    @PreAuthorize("@ss.hasPermission('ai-video:webhook:test')")
    public CommonResult<Long> test(@RequestParam("id") Long id) {
        return success(webhookService.createTestDelivery(id));
    }

    @GetMapping("/delivery/page")
    @Operation(summary = "获取 Webhook 投递记录分页")
    @PreAuthorize("@ss.hasPermission('ai-video:webhook:query')")
    public CommonResult<PageResult<WebhookDeliveryRespVO>> getDeliveryPage(
            @Valid WebhookDeliveryPageReqVO reqVO) {
        return success(webhookService.getDeliveryPage(reqVO));
    }

    @GetMapping("/delivery/get")
    @Operation(summary = "获取 Webhook 投递详情")
    @PreAuthorize("@ss.hasPermission('ai-video:webhook:query')")
    public CommonResult<WebhookDeliveryRespVO> getDelivery(@RequestParam("id") Long id) {
        return success(webhookService.getDelivery(id));
    }

    @PostMapping("/delivery/replay")
    @Operation(summary = "重放 Webhook 死信")
    @PreAuthorize("@ss.hasPermission('ai-video:webhook:replay')")
    public CommonResult<Boolean> replay(@RequestParam("id") Long id) {
        webhookService.replay(id);
        return success(true);
    }
}
