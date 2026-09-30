package com.linsight.module.aivideo.controller.admin.camera;

import com.linsight.framework.apilog.core.annotation.ApiAccessLog;
import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.framework.common.pojo.PageResult;
import com.linsight.framework.common.util.object.BeanUtils;
import com.linsight.module.aivideo.controller.admin.camera.vo.CameraPageReqVO;
import com.linsight.module.aivideo.controller.admin.camera.vo.CameraRespVO;
import com.linsight.module.aivideo.controller.admin.camera.vo.CameraSaveReqVO;
import com.linsight.module.aivideo.controller.admin.camera.vo.PreviewSessionCreateReqVO;
import com.linsight.module.aivideo.controller.admin.camera.vo.PreviewSessionRespVO;
import com.linsight.module.aivideo.controller.admin.camera.vo.StreamCheckCreateReqVO;
import com.linsight.module.aivideo.controller.admin.camera.vo.StreamCheckRespVO;
import com.linsight.module.aivideo.controller.admin.camera.vo.WebRtcOfferReqVO;
import com.linsight.module.aivideo.convert.camera.CameraConvert;
import com.linsight.module.aivideo.service.camera.CameraService;
import com.linsight.module.aivideo.service.camera.CameraOverviewService;
import com.linsight.module.aivideo.service.camera.PreviewMedia;
import com.linsight.module.aivideo.service.camera.PreviewService;
import com.linsight.module.aivideo.service.camera.StreamCheckService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.annotation.Resource;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import org.springframework.http.CacheControl;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import static com.linsight.framework.common.pojo.CommonResult.success;
import static com.linsight.framework.web.core.util.WebFrameworkUtils.getLoginUserId;
import static com.linsight.framework.web.core.util.WebFrameworkUtils.getTenantId;

@Tag(name = "管理后台 - 摄像头")
@RestController
@RequestMapping("/ai-video/camera")
@Validated
public class CameraController {

    @Resource
    private CameraService cameraService;
    @Resource
    private CameraOverviewService cameraOverviewService;
    @Resource
    private StreamCheckService streamCheckService;
    @Resource
    private PreviewService previewService;

    @PostMapping("/create")
    @Operation(summary = "创建摄像头")
    @PreAuthorize("@ss.hasPermission('ai-video:camera:create')")
    @ApiAccessLog(sanitizeKeys = {"mainStreamUri", "subStreamUri", "username", "password"})
    public CommonResult<Long> createCamera(@Valid @RequestBody CameraSaveReqVO reqVO) {
        return success(cameraService.createCamera(reqVO));
    }

    @PutMapping("/update")
    @Operation(summary = "修改摄像头", description = "码流 URI、用户名和密码留空表示保留原值")
    @PreAuthorize("@ss.hasPermission('ai-video:camera:update')")
    @ApiAccessLog(sanitizeKeys = {"mainStreamUri", "subStreamUri", "username", "password"})
    public CommonResult<Boolean> updateCamera(@Valid @RequestBody CameraSaveReqVO reqVO) {
        cameraService.updateCamera(reqVO);
        return success(true);
    }

    @DeleteMapping("/delete")
    @Operation(summary = "删除摄像头")
    @Parameter(name = "id", description = "摄像头编号", required = true)
    @PreAuthorize("@ss.hasPermission('ai-video:camera:delete')")
    public CommonResult<Boolean> deleteCamera(@RequestParam("id") Long id) {
        cameraService.deleteCamera(id);
        return success(true);
    }

    @GetMapping("/get")
    @Operation(summary = "获取摄像头安全详情")
    @PreAuthorize("@ss.hasPermission('ai-video:camera:query')")
    public CommonResult<CameraRespVO> getCamera(@RequestParam("id") Long id) {
        var camera = CameraConvert.INSTANCE.convert(cameraService.getCamera(id));
        if (camera != null) cameraOverviewService.enrichCapabilities(java.util.List.of(camera));
        return success(camera);
    }

    @GetMapping("/page")
    @Operation(summary = "获取摄像头分页")
    @PreAuthorize("@ss.hasPermission('ai-video:camera:query')")
    public CommonResult<PageResult<CameraRespVO>> getCameraPage(@Valid CameraPageReqVO reqVO) {
        var page = CameraConvert.INSTANCE.convertPage(cameraService.getCameraPage(reqVO));
        cameraOverviewService.enrichCapabilities(page.getList());
        return success(page);
    }

    @PostMapping("/check/create")
    @Operation(summary = "创建异步摄像头连通检测", description = "V1 由管理员显式指定执行节点")
    @PreAuthorize("@ss.hasPermission('ai-video:camera:check')")
    public CommonResult<Long> createStreamCheck(@Valid @RequestBody StreamCheckCreateReqVO reqVO) {
        return success(streamCheckService.createStreamCheck(reqVO.getCameraId(), reqVO.getNodeId()));
    }

    @GetMapping("/check/get")
    @Operation(summary = "获取摄像头连通检测结果")
    @PreAuthorize("@ss.hasPermission('ai-video:camera:query')")
    public CommonResult<StreamCheckRespVO> getStreamCheck(@RequestParam("id") Long id) {
        return success(BeanUtils.toBean(streamCheckService.getStreamCheck(id), StreamCheckRespVO.class));
    }

    @Resource
    private com.linsight.module.aivideo.service.camera.CameraDisplayPreferenceService displayPreferenceService;

    @GetMapping("/display-preference/get")
    @PreAuthorize("@ss.hasPermission('ai-video:camera:preview')")
    public CommonResult<java.util.List<String>> getDisplayPreference(@RequestParam Long cameraId, HttpServletRequest request) {
        return success(displayPreferenceService.get(getLoginUserId(request), cameraId));
    }

    @PutMapping("/display-preference/update")
    @PreAuthorize("@ss.hasPermission('ai-video:camera:preview')")
    public CommonResult<Boolean> updateDisplayPreference(@Valid @RequestBody com.linsight.module.aivideo.controller.admin.camera.vo.CameraDisplayPreferenceSaveReqVO reqVO, HttpServletRequest request) {
        displayPreferenceService.save(getLoginUserId(request), reqVO.getCameraId(), reqVO.getHiddenLayers());
        return success(true);
    }

    @PostMapping("/preview/create")
    @Operation(summary = "创建单路浏览器预览会话")
    @PreAuthorize("@ss.hasPermission('ai-video:camera:preview')")
    public CommonResult<PreviewSessionRespVO> createPreview(
            @Valid @RequestBody PreviewSessionCreateReqVO reqVO, HttpServletRequest request) {
        return success(previewService.createPreview(reqVO.getCameraId(), reqVO.getNodeId(), reqVO.getStreamType(),
                getTenantId(request), getLoginUserId(request)));
    }

    @PostMapping("/preview/webrtc/offer")
    @Operation(summary = "通过 WebRTC Offer 创建与识别任务同源的预览会话")
    @PreAuthorize("@ss.hasPermission('ai-video:camera:preview')")
    @ApiAccessLog(enable = false)
    public CommonResult<PreviewSessionRespVO> createWebRtcPreview(
            @Valid @RequestBody WebRtcOfferReqVO reqVO, HttpServletRequest request) {
        return success(previewService.createWebRtcPreview(reqVO.getCameraId(), reqVO.getNodeId(),
                reqVO.getOfferSdp(), reqVO.getOfferType(), getTenantId(request), getLoginUserId(request)));
    }

    @GetMapping("/preview/get")
    @Operation(summary = "获取单路预览会话状态")
    @PreAuthorize("@ss.hasPermission('ai-video:camera:preview')")
    public CommonResult<PreviewSessionRespVO> getPreview(@RequestParam("sessionId") String sessionId,
                                                         HttpServletRequest request) {
        return success(previewService.getPreview(sessionId, getTenantId(request), getLoginUserId(request)));
    }

    @GetMapping("/preview/media/{sessionId}/{fileName}")
    @Operation(summary = "代理预览 HLS 媒体")
    @PreAuthorize("@ss.hasPermission('ai-video:camera:preview')")
    @ApiAccessLog(enable = false)
    public ResponseEntity<byte[]> getPreviewMedia(@PathVariable String sessionId,
                                                   @PathVariable String fileName,
                                                   HttpServletRequest request) {
        PreviewMedia media = previewService.getMedia(sessionId, fileName, getTenantId(request),
                getLoginUserId(request));
        return ResponseEntity.ok().contentType(MediaType.parseMediaType(media.getContentType()))
                .cacheControl(CacheControl.noStore()).body(media.getBody());
    }

    @DeleteMapping("/preview/delete")
    @Operation(summary = "释放单路预览会话")
    @PreAuthorize("@ss.hasPermission('ai-video:camera:preview')")
    public CommonResult<Boolean> releasePreview(@RequestParam("sessionId") String sessionId,
                                                HttpServletRequest request) {
        previewService.releasePreview(sessionId, getTenantId(request), getLoginUserId(request));
        return success(true);
    }

}
