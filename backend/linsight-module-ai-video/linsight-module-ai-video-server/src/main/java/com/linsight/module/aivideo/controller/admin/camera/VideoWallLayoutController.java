package com.linsight.module.aivideo.controller.admin.camera;

import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.module.aivideo.controller.admin.camera.vo.VideoWallLayoutRespVO;
import com.linsight.module.aivideo.controller.admin.camera.vo.VideoWallLayoutSaveReqVO;
import com.linsight.module.aivideo.service.camera.VideoWallLayoutService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.annotation.Resource;
import jakarta.validation.Valid;
import jakarta.servlet.http.HttpServletRequest;
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

import java.util.List;

import static com.linsight.framework.common.pojo.CommonResult.success;
import static com.linsight.framework.web.core.util.WebFrameworkUtils.getLoginUserId;

@Tag(name = "管理后台 - 视频墙布局方案")
@RestController
@RequestMapping("/ai-video/camera/wall-layout")
@Validated
public class VideoWallLayoutController {

    @Resource
    private VideoWallLayoutService layoutService;

    @GetMapping("/list")
    @Operation(summary = "获取当前用户的视频墙布局方案")
    @PreAuthorize("@ss.hasPermission('ai-video:camera:preview')")
    public CommonResult<List<VideoWallLayoutRespVO>> getLayouts(HttpServletRequest request) {
        return success(layoutService.getLayouts(getLoginUserId(request)));
    }

    @PostMapping("/create")
    @Operation(summary = "创建视频墙布局方案")
    @PreAuthorize("@ss.hasPermission('ai-video:camera:preview')")
    public CommonResult<Long> createLayout(@Valid @RequestBody VideoWallLayoutSaveReqVO reqVO,
                                            HttpServletRequest request) {
        return success(layoutService.createLayout(reqVO, getLoginUserId(request)));
    }

    @PutMapping("/update")
    @Operation(summary = "覆盖视频墙布局方案")
    @PreAuthorize("@ss.hasPermission('ai-video:camera:preview')")
    public CommonResult<Boolean> updateLayout(@Valid @RequestBody VideoWallLayoutSaveReqVO reqVO,
                                               HttpServletRequest request) {
        layoutService.updateLayout(reqVO, getLoginUserId(request));
        return success(true);
    }

    @PutMapping("/activate")
    @Operation(summary = "激活视频墙布局方案")
    @PreAuthorize("@ss.hasPermission('ai-video:camera:preview')")
    public CommonResult<Boolean> activateLayout(@RequestParam("id") Long id, HttpServletRequest request) {
        layoutService.activateLayout(id, getLoginUserId(request));
        return success(true);
    }

    @DeleteMapping("/delete")
    @Operation(summary = "删除视频墙布局方案")
    @PreAuthorize("@ss.hasPermission('ai-video:camera:preview')")
    public CommonResult<Boolean> deleteLayout(@RequestParam("id") Long id, HttpServletRequest request) {
        layoutService.deleteLayout(id, getLoginUserId(request));
        return success(true);
    }

}
