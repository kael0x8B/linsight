package com.linsight.module.aivideo.service.camera;

import cn.hutool.core.util.ObjectUtil;
import com.linsight.framework.common.util.object.BeanUtils;
import com.linsight.module.aivideo.controller.admin.camera.vo.CameraGroupListReqVO;
import com.linsight.module.aivideo.controller.admin.camera.vo.CameraGroupSaveReqVO;
import com.linsight.module.aivideo.dal.dataobject.camera.CameraGroupDO;
import com.linsight.module.aivideo.dal.mysql.camera.CameraGroupMapper;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;

import java.util.List;
import java.util.Objects;

import static com.linsight.framework.common.exception.util.ServiceExceptionUtil.exception;
import static com.linsight.module.aivideo.enums.camera.ErrorCodeConstants.*;

@Service
@Validated
public class CameraGroupServiceImpl implements CameraGroupService {

    @Resource
    private CameraGroupMapper cameraGroupMapper;

    @Override
    public Long createCameraGroup(CameraGroupSaveReqVO createReqVO) {
        Long parentId = normalizeParentId(createReqVO.getParentId());
        CameraGroupDO parent = validateParent(null, parentId);
        validateNameUnique(null, parentId, createReqVO.getName());
        CameraGroupDO group = BeanUtils.toBean(createReqVO, CameraGroupDO.class);
        group.setParentId(parentId);
        group.setPath(buildChildPath(parent));
        cameraGroupMapper.insert(group);
        return group.getId();
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void updateCameraGroup(CameraGroupSaveReqVO updateReqVO) {
        CameraGroupDO current = validateExists(updateReqVO.getId());
        Long parentId = normalizeParentId(updateReqVO.getParentId());
        CameraGroupDO parent = validateParent(updateReqVO.getId(), parentId);
        validateNameUnique(updateReqVO.getId(), parentId, updateReqVO.getName());

        String newPath = buildChildPath(parent);
        if (!Objects.equals(current.getPath(), newPath)) {
            moveDescendants(current, newPath);
        }
        CameraGroupDO update = BeanUtils.toBean(updateReqVO, CameraGroupDO.class);
        update.setParentId(parentId);
        update.setPath(newPath);
        cameraGroupMapper.updateById(update);
    }

    @Override
    public void deleteCameraGroup(Long id) {
        validateExists(id);
        if (cameraGroupMapper.selectCountByParentId(id) > 0) {
            throw exception(CAMERA_GROUP_HAS_CHILDREN);
        }
        if (cameraGroupMapper.selectCameraCountByGroupId(id) > 0) {
            throw exception(CAMERA_GROUP_HAS_CAMERAS);
        }
        cameraGroupMapper.deleteById(id);
    }

    @Override
    public CameraGroupDO getCameraGroup(Long id) {
        return validateExists(id);
    }

    @Override
    public List<CameraGroupDO> getCameraGroupList(CameraGroupListReqVO listReqVO) {
        return cameraGroupMapper.selectList(listReqVO.getName(), listReqVO.getStatus());
    }

    private CameraGroupDO validateExists(Long id) {
        CameraGroupDO group = cameraGroupMapper.selectById(id);
        if (group == null) {
            throw exception(CAMERA_GROUP_NOT_FOUND);
        }
        return group;
    }

    private CameraGroupDO validateParent(Long id, Long parentId) {
        if (CameraGroupDO.ROOT_PARENT_ID.equals(parentId)) {
            return null;
        }
        if (Objects.equals(id, parentId)) {
            throw exception(CAMERA_GROUP_PARENT_ERROR);
        }
        CameraGroupDO parent = cameraGroupMapper.selectById(parentId);
        if (parent == null) {
            throw exception(CAMERA_GROUP_NOT_FOUND);
        }
        if (id != null && parent.getPath().contains("/" + id + "/")) {
            throw exception(CAMERA_GROUP_PARENT_IS_CHILD);
        }
        return parent;
    }

    private void validateNameUnique(Long id, Long parentId, String name) {
        CameraGroupDO sameName = cameraGroupMapper.selectByParentIdAndName(parentId, name);
        if (sameName != null && ObjectUtil.notEqual(sameName.getId(), id)) {
            throw exception(CAMERA_GROUP_NAME_DUPLICATE);
        }
    }

    private void moveDescendants(CameraGroupDO current, String newPath) {
        String oldPrefix = current.getPath() + current.getId() + "/";
        String newPrefix = newPath + current.getId() + "/";
        for (CameraGroupDO descendant : cameraGroupMapper.selectDescendants(oldPrefix)) {
            CameraGroupDO update = new CameraGroupDO();
            update.setId(descendant.getId());
            update.setPath(newPrefix + descendant.getPath().substring(oldPrefix.length()));
            cameraGroupMapper.updateById(update);
        }
    }

    private static Long normalizeParentId(Long parentId) {
        return parentId == null ? CameraGroupDO.ROOT_PARENT_ID : parentId;
    }

    private static String buildChildPath(CameraGroupDO parent) {
        return parent == null ? CameraGroupDO.ROOT_PATH : parent.getPath() + parent.getId() + "/";
    }

}
