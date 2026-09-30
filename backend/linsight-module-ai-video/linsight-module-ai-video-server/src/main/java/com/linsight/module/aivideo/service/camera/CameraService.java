package com.linsight.module.aivideo.service.camera;

import com.linsight.framework.common.pojo.PageResult;
import com.linsight.module.aivideo.controller.admin.camera.vo.CameraPageReqVO;
import com.linsight.module.aivideo.controller.admin.camera.vo.CameraSaveReqVO;
import com.linsight.module.aivideo.dal.dataobject.camera.CameraDO;

public interface CameraService {
    /** Tenant-scoped display names only; credentials and domain entities never cross this query contract. */
    java.util.Map<Long, String> getCameraNames(java.util.Collection<Long> ids);

    Long createCamera(CameraSaveReqVO createReqVO);

    void updateCamera(CameraSaveReqVO updateReqVO);

    void deleteCamera(Long id);

    CameraDO getCamera(Long id);

    PageResult<CameraDO> getCameraPage(CameraPageReqVO pageReqVO);

    /**
     * 仅向受信任 Runtime 提供可拉取的码流地址，不得返回给管理端。
     */
    String getRuntimeStreamUrl(Long id, String streamType);

    /** Configured alternatives for encrypted storage on the owning gateway; never a browser response. */
    java.util.Map<String, String> getRuntimeStreamUrls(Long id);

}
