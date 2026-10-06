package com.linsight.module.aivideo.controller.admin.node;

import com.linsight.framework.common.pojo.*;
import com.linsight.framework.common.util.object.BeanUtils;
import com.linsight.module.aivideo.controller.admin.node.vo.*;
import com.linsight.module.aivideo.service.node.NodeApplicationReleaseService;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.annotation.Resource;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;
import java.util.List;
import static com.linsight.framework.common.pojo.CommonResult.success;

@RestController
@RequestMapping("/ai-video/node/application-release")
@Validated
@Tag(name="管理后台 - 盒子升级包构建")
public class NodeApplicationReleaseController {
    @Resource private NodeApplicationReleaseService service;
    @PreAuthorize("@ss.hasPermission('ai-video:node:upgrade')")
    @GetMapping("/profiles")
    public CommonResult<List<NodeApplicationReleaseService.ProfileView>> profiles() { return success(service.profiles()); }
    @PreAuthorize("@ss.hasPermission('ai-video:node:upgrade')")
    @GetMapping("/configuration")
    public CommonResult<NodeApplicationReleaseService.BuildView> configuration() { return success(service.configuration()); }
    @PreAuthorize("@ss.hasPermission('ai-video:node:upgrade')")
    @PostMapping("/create")
    public CommonResult<Long> create(@Valid @RequestBody NodeApplicationReleaseCreateReqVO request) {
        return success(service.create(request));
    }
    @PreAuthorize("@ss.hasPermission('ai-video:node:upgrade')")
    @GetMapping("/page")
    public CommonResult<PageResult<NodeApplicationReleaseRespVO>> page(@Valid PageParam page) {
        var result = service.page(page);
        return success(new PageResult<>(BeanUtils.toBean(result.getList(), NodeApplicationReleaseRespVO.class), result.getTotal()));
    }
    @PreAuthorize("@ss.hasPermission('ai-video:node:upgrade')")
    @PostMapping("/retry")
    public CommonResult<Boolean> retry(@RequestParam Long id) { service.retry(id); return success(true); }
    @PreAuthorize("@ss.hasPermission('ai-video:node:upgrade')")
    @GetMapping("/download-url")
    @com.linsight.framework.apilog.core.annotation.ApiAccessLog(responseEnable=false)
    public CommonResult<String> download(@RequestParam Long id, @RequestParam String artifact) {
        return success(service.download(id, artifact));
    }
}
