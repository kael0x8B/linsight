package com.linsight.module.aivideo.service.camera;

import com.linsight.framework.common.exception.ServiceException;
import com.linsight.module.aivideo.controller.admin.camera.vo.CameraGroupSaveReqVO;
import com.linsight.module.aivideo.dal.dataobject.camera.CameraGroupDO;
import com.linsight.module.aivideo.dal.mysql.camera.CameraGroupMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class CameraGroupServiceImplTest {

    @Mock
    private CameraGroupMapper cameraGroupMapper;
    @InjectMocks
    private CameraGroupServiceImpl cameraGroupService;

    @Test
    void createNestedGroupMustDerivePathFromParent() {
        CameraGroupDO parent = group(10L, 0L, "/");
        when(cameraGroupMapper.selectById(10L)).thenReturn(parent);

        CameraGroupSaveReqVO create = saveReqVO(null, 10L, "二号厂区");
        cameraGroupService.createCameraGroup(create);

        ArgumentCaptor<CameraGroupDO> captor = ArgumentCaptor.forClass(CameraGroupDO.class);
        verify(cameraGroupMapper).insert(captor.capture());
        assertEquals(10L, captor.getValue().getParentId());
        assertEquals("/10/", captor.getValue().getPath());
    }

    @Test
    void updateMustRejectMovingGroupBelowItsDescendant() {
        CameraGroupDO current = group(10L, 0L, "/");
        CameraGroupDO descendant = group(11L, 10L, "/10/");
        when(cameraGroupMapper.selectById(10L)).thenReturn(current);
        when(cameraGroupMapper.selectById(11L)).thenReturn(descendant);

        ServiceException exception = assertThrows(ServiceException.class,
                () -> cameraGroupService.updateCameraGroup(saveReqVO(10L, 11L, "一号厂区")));

        assertEquals(1_020_000_003, exception.getCode());
        verify(cameraGroupMapper, never()).updateById(any(CameraGroupDO.class));
    }

    @Test
    void updateMustRewriteEveryDescendantPathWhenMovingSubtree() {
        CameraGroupDO current = group(10L, 1L, "/1/");
        CameraGroupDO newParent = group(20L, 2L, "/2/");
        CameraGroupDO child = group(11L, 10L, "/1/10/");
        CameraGroupDO grandchild = group(12L, 11L, "/1/10/11/");
        when(cameraGroupMapper.selectById(10L)).thenReturn(current);
        when(cameraGroupMapper.selectById(20L)).thenReturn(newParent);
        when(cameraGroupMapper.selectDescendants("/1/10/"))
                .thenReturn(List.of(child, grandchild));

        cameraGroupService.updateCameraGroup(saveReqVO(10L, 20L, "一号厂区"));

        ArgumentCaptor<CameraGroupDO> captor = ArgumentCaptor.forClass(CameraGroupDO.class);
        verify(cameraGroupMapper, times(3)).updateById(captor.capture());
        List<CameraGroupDO> updates = captor.getAllValues();
        assertEquals("/2/20/10/", updates.get(0).getPath());
        assertEquals("/2/20/10/11/", updates.get(1).getPath());
        assertEquals("/2/20/", updates.get(2).getPath());
        assertEquals(20L, updates.get(2).getParentId());
    }

    @Test
    void deleteMustRejectGroupWithChildrenBeforeCheckingCameras() {
        when(cameraGroupMapper.selectById(10L)).thenReturn(group(10L, 0L, "/"));
        when(cameraGroupMapper.selectCountByParentId(10L)).thenReturn(1L);

        ServiceException exception = assertThrows(ServiceException.class,
                () -> cameraGroupService.deleteCameraGroup(10L));

        assertEquals(1_020_000_004, exception.getCode());
        verify(cameraGroupMapper, never()).selectCameraCountByGroupId(anyLong());
        verify(cameraGroupMapper, never()).deleteById(anyLong());
    }

    @Test
    void deleteMustRejectGroupContainingCameras() {
        when(cameraGroupMapper.selectById(10L)).thenReturn(group(10L, 0L, "/"));
        when(cameraGroupMapper.selectCountByParentId(10L)).thenReturn(0L);
        when(cameraGroupMapper.selectCameraCountByGroupId(10L)).thenReturn(2L);

        ServiceException exception = assertThrows(ServiceException.class,
                () -> cameraGroupService.deleteCameraGroup(10L));

        assertEquals(1_020_000_005, exception.getCode());
        verify(cameraGroupMapper, never()).deleteById(anyLong());
    }

    private static CameraGroupSaveReqVO saveReqVO(Long id, Long parentId, String name) {
        CameraGroupSaveReqVO reqVO = new CameraGroupSaveReqVO();
        reqVO.setId(id);
        reqVO.setParentId(parentId);
        reqVO.setName(name);
        reqVO.setSort(10);
        reqVO.setStatus(0);
        return reqVO;
    }

    private static CameraGroupDO group(Long id, Long parentId, String path) {
        CameraGroupDO group = new CameraGroupDO();
        group.setId(id);
        group.setName("分组-" + id);
        group.setParentId(parentId);
        group.setPath(path);
        group.setSort(10);
        group.setStatus(0);
        return group;
    }

}
