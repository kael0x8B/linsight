package com.linsight.module.aivideo.service.camera;

import com.linsight.module.aivideo.controller.admin.camera.vo.CameraGroupListReqVO;
import com.linsight.module.aivideo.controller.admin.camera.vo.CameraGroupSaveReqVO;
import com.linsight.module.aivideo.dal.dataobject.camera.CameraGroupDO;

import java.util.List;

public interface CameraGroupService {

    Long createCameraGroup(CameraGroupSaveReqVO createReqVO);

    void updateCameraGroup(CameraGroupSaveReqVO updateReqVO);

    void deleteCameraGroup(Long id);

    CameraGroupDO getCameraGroup(Long id);

    List<CameraGroupDO> getCameraGroupList(CameraGroupListReqVO listReqVO);

}
