package com.linsight.module.aivideo.service.camera;

import com.linsight.framework.common.exception.ServiceException;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.module.aivideo.controller.admin.camera.vo.VideoWallLayoutRespVO;
import com.linsight.module.aivideo.controller.admin.camera.vo.VideoWallLayoutSaveReqVO;
import com.linsight.module.aivideo.dal.dataobject.camera.CameraDO;
import com.linsight.module.aivideo.dal.dataobject.camera.VideoWallLayoutDO;
import com.linsight.module.aivideo.dal.mysql.camera.CameraMapper;
import com.linsight.module.aivideo.dal.mysql.camera.VideoWallLayoutMapper;
import com.linsight.module.aivideo.service.node.NodeService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.Arrays;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class VideoWallLayoutServiceImplTest {

    @Mock
    private VideoWallLayoutMapper layoutMapper;
    @Mock
    private CameraMapper cameraMapper;
    @Mock
    private NodeService nodeService;
    @InjectMocks
    private VideoWallLayoutServiceImpl layoutService;

    @Test
    void createMustPreserveEmptyCellPositions() {
        VideoWallLayoutSaveReqVO request = request(null, 2, 4, Arrays.asList(10L, null, 11L, null));
        when(cameraMapper.selectBatchIds(List.of(10L, 11L))).thenReturn(List.of(camera(10L), camera(11L)));

        layoutService.createLayout(request, 7L);

        ArgumentCaptor<VideoWallLayoutDO> captor = ArgumentCaptor.forClass(VideoWallLayoutDO.class);
        verify(layoutMapper).insert(captor.capture());
        VideoWallLayoutDO saved = captor.getValue();
        assertEquals(7L, saved.getUserId());
        assertEquals("1.2", saved.getSchemaVersion());
        assertEquals(3L, saved.getNodeId());
        List<?> cameraIds = JsonUtils.parseObject(saved.getCameraIdsJson(), List.class);
        assertEquals(4, cameraIds.size());
        assertNull(cameraIds.get(1));
    }

    @Test
    void createMustRejectCameraCountThatDoesNotMatchSplit() {
        VideoWallLayoutSaveReqVO request = request(null, 1, 9, Arrays.asList(10L, null, null, null));

        ServiceException exception = assertThrows(ServiceException.class,
                () -> layoutService.createLayout(request, 7L));

        assertEquals(1_020_000_132, exception.getCode());
        verify(layoutMapper, never()).insert(any(VideoWallLayoutDO.class));
    }

    @Test
    void activateMustOnlyChangeOwnedLayout() {
        VideoWallLayoutDO layout = layout(20L, 7L);
        when(layoutMapper.selectById(20L)).thenReturn(layout);

        layoutService.activateLayout(20L, 7L);

        verify(layoutMapper).deactivateAll(7L);
        ArgumentCaptor<VideoWallLayoutDO> captor = ArgumentCaptor.forClass(VideoWallLayoutDO.class);
        verify(layoutMapper).updateById(captor.capture());
        assertEquals(Boolean.TRUE, captor.getValue().getActive());
    }

    @Test
    void listMustNeverExposeAnotherUsersRows() {
        VideoWallLayoutDO layout = layout(20L, 7L);
        layout.setCameraIdsJson("[10,null,11,null]");
        layout.setSplitCount(4);
        layout.setSlotIndex(1);
        layout.setSchemaVersion("1.0");
        layout.setName("方案 1");
        when(layoutMapper.selectListByUserId(7L)).thenReturn(List.of(layout));

        List<VideoWallLayoutRespVO> result = layoutService.getLayouts(7L);

        assertEquals(1, result.size());
        assertEquals(Arrays.asList(10L, null, 11L, null), result.get(0).getCameraIds());
        verify(layoutMapper).selectListByUserId(7L);
    }

    private static VideoWallLayoutSaveReqVO request(Long id, int slotIndex, int splitCount,
                                                     List<Long> cameraIds) {
        VideoWallLayoutSaveReqVO request = new VideoWallLayoutSaveReqVO();
        request.setId(id);
        request.setSlotIndex(slotIndex);
        request.setName("方案 " + slotIndex);
        request.setSplitCount(splitCount);
        request.setNodeId(3L);
        request.setCameraIds(cameraIds);
        return request;
    }

    private static CameraDO camera(Long id) {
        CameraDO camera = new CameraDO();
        camera.setId(id);
        return camera;
    }

    private static VideoWallLayoutDO layout(Long id, Long userId) {
        VideoWallLayoutDO layout = new VideoWallLayoutDO();
        layout.setId(id);
        layout.setUserId(userId);
        return layout;
    }

}
