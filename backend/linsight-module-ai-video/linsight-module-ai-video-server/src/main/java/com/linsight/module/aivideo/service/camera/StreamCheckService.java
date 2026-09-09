package com.linsight.module.aivideo.service.camera;

import com.linsight.module.aivideo.controller.node.camera.vo.StreamCheckReportReqVO;
import com.linsight.module.aivideo.controller.node.camera.vo.StreamCheckTaskRespVO;
import com.linsight.module.aivideo.dal.dataobject.camera.CameraStreamCheckDO;

public interface StreamCheckService {

    Long createStreamCheck(Long cameraId, Long nodeId);

    StreamCheckTaskRespVO claimStreamCheck(Long nodeId);

    void reportStreamCheck(Long nodeId, StreamCheckReportReqVO reqVO);

    CameraStreamCheckDO getStreamCheck(Long id);

}
