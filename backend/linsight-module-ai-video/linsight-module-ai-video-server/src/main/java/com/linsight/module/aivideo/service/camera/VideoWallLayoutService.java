package com.linsight.module.aivideo.service.camera;

import com.linsight.module.aivideo.controller.admin.camera.vo.VideoWallLayoutRespVO;
import com.linsight.module.aivideo.controller.admin.camera.vo.VideoWallLayoutSaveReqVO;

import java.util.List;

public interface VideoWallLayoutService {

    List<VideoWallLayoutRespVO> getLayouts(Long userId);

    Long createLayout(VideoWallLayoutSaveReqVO reqVO, Long userId);

    void updateLayout(VideoWallLayoutSaveReqVO reqVO, Long userId);

    void activateLayout(Long id, Long userId);

    void deleteLayout(Long id, Long userId);

}
