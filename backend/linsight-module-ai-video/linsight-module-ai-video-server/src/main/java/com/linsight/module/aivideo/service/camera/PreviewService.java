package com.linsight.module.aivideo.service.camera;

import com.linsight.module.aivideo.controller.admin.camera.vo.PreviewSessionRespVO;
import com.linsight.module.aivideo.controller.node.camera.vo.NodeOverlayReportReqVO;

public interface PreviewService {

    PreviewSessionRespVO createPreview(Long cameraId, Long nodeId, String streamType,
                                       Long tenantId, Long userId);

    PreviewSessionRespVO createWebRtcPreview(Long cameraId, Long nodeId, String offerSdp,
                                             String offerType, Long tenantId, Long userId);

    PreviewSessionRespVO getPreview(String sessionId, Long tenantId, Long userId);

    PreviewMedia getMedia(String sessionId, String fileName, Long tenantId, Long userId);

    void releasePreview(String sessionId, Long tenantId, Long userId);

    void publishOverlay(NodeOverlayReportReqVO reqVO, Long nodeId);

}
