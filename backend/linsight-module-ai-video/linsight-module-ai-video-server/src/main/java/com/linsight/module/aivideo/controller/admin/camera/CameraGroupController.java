package com.linsight.module.aivideo.controller.admin.camera;

import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.framework.common.util.object.BeanUtils;
import com.linsight.module.aivideo.controller.admin.camera.vo.CameraGroupListReqVO;
import com.linsight.module.aivideo.controller.admin.camera.vo.CameraGroupRespVO;
import com.linsight.module.aivideo.controller.admin.camera.vo.CameraGroupSaveReqVO;
import com.linsight.module.aivideo.service.camera.CameraGroupService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.annotation.Resource;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import java.util.List;

import static com.linsight.framework.common.pojo.CommonResult.success;

@Tag(name = "管理后台 - 摄像头分组")
@RestController
@RequestMapping("/ai-video/camera/group")
@Validated
public class CameraGroupController {

    @Resource
    private CameraGroupService cameraGroupService;

    @PostMapping("/create")
    @Operation(summary = "创建摄像头分组")
    @PreAuthorize("@ss.hasPermission('ai-video:camera:create')")
    public CommonResult<Long> createCameraGroup(@Valid @RequestBody CameraGroupSaveReqVO reqVO) {
        return success(cameraGroupService.createCameraGroup(reqVO));
    }

    @PutMapping("/update")
    @Operation(summary = "修改摄像头分组")
    @PreAuthorize("@ss.hasPermission('ai-video:camera:update')")
    public CommonResult<Boolean> updateCameraGroup(@Valid @RequestBody CameraGroupSaveReqVO reqVO) {
        cameraGroupService.updateCameraGroup(reqVO);
        return success(true);
    }

    @DeleteMapping("/delete")
    @Operation(summary = "删除空摄像头分组")
    @Parameter(name = "id", description = "分组编号", required = true)
    @PreAuthorize("@ss.hasPermission('ai-video:camera:delete')")
    public CommonResult<Boolean> deleteCameraGroup(@RequestParam("id") Long id) {
        cameraGroupService.deleteCameraGroup(id);
        return success(true);
    }

    @GetMapping("/get")
    @Operation(summary = "获取摄像头分组")
    @PreAuthorize("@ss.hasPermission('ai-video:camera:query')")
    public CommonResult<CameraGroupRespVO> getCameraGroup(@RequestParam("id") Long id) {
        return success(BeanUtils.toBean(cameraGroupService.getCameraGroup(id), CameraGroupRespVO.class));
    }

    @GetMapping("/list")
    @Operation(summary = "获取摄像头分组树形数据")
    @PreAuthorize("@ss.hasPermission('ai-video:camera:query')")
    public CommonResult<List<CameraGroupRespVO>> getCameraGroupList(@Valid CameraGroupListReqVO reqVO) {
        return success(BeanUtils.toBean(cameraGroupService.getCameraGroupList(reqVO), CameraGroupRespVO.class));
    }

}
