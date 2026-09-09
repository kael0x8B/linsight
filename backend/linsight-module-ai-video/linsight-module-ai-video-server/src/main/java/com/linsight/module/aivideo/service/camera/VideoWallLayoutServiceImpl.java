package com.linsight.module.aivideo.service.camera;

import com.fasterxml.jackson.core.type.TypeReference;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.module.aivideo.controller.admin.camera.vo.VideoWallLayoutRespVO;
import com.linsight.module.aivideo.controller.admin.camera.vo.VideoWallLayoutSaveReqVO;
import com.linsight.module.aivideo.dal.dataobject.camera.CameraDO;
import com.linsight.module.aivideo.dal.dataobject.camera.VideoWallLayoutDO;
import com.linsight.module.aivideo.dal.mysql.camera.CameraMapper;
import com.linsight.module.aivideo.dal.mysql.camera.VideoWallLayoutMapper;
import com.linsight.module.aivideo.service.node.NodeService;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;

import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

import static com.linsight.framework.common.exception.util.ServiceExceptionUtil.exception;
import static com.linsight.module.aivideo.enums.camera.ErrorCodeConstants.CAMERA_NOT_FOUND;
import static com.linsight.module.aivideo.enums.camera.ErrorCodeConstants.VIDEO_WALL_LAYOUT_NOT_FOUND;
import static com.linsight.module.aivideo.enums.camera.ErrorCodeConstants.VIDEO_WALL_LAYOUT_SLOT_OCCUPIED;
import static com.linsight.module.aivideo.enums.camera.ErrorCodeConstants.VIDEO_WALL_LAYOUT_SPLIT_INVALID;

@Service
@Validated
public class VideoWallLayoutServiceImpl implements VideoWallLayoutService {

    private static final String SCHEMA_VERSION = "1.2";
    private static final Set<Integer> SUPPORTED_SPLITS = Set.of(1, 4, 9, 16);
    private static final TypeReference<List<Long>> LONG_LIST = new TypeReference<>() { };

    @Resource
    private VideoWallLayoutMapper layoutMapper;
    @Resource
    private CameraMapper cameraMapper;
    @Resource
    private NodeService nodeService;

    @Override
    public List<VideoWallLayoutRespVO> getLayouts(Long userId) {
        return layoutMapper.selectListByUserId(userId).stream().map(this::convert).toList();
    }

    @Override
    public Long createLayout(VideoWallLayoutSaveReqVO reqVO, Long userId) {
        if (layoutMapper.selectByUserAndSlot(userId, reqVO.getSlotIndex()) != null) {
            throw exception(VIDEO_WALL_LAYOUT_SLOT_OCCUPIED);
        }
        validateLayout(reqVO);
        VideoWallLayoutDO layout = toDataObject(reqVO, userId);
        layout.setActive(false);
        layoutMapper.insert(layout);
        return layout.getId();
    }

    @Override
    public void updateLayout(VideoWallLayoutSaveReqVO reqVO, Long userId) {
        VideoWallLayoutDO current = validateOwnedLayout(reqVO.getId(), userId);
        if (!Objects.equals(current.getSlotIndex(), reqVO.getSlotIndex())) {
            VideoWallLayoutDO occupied = layoutMapper.selectByUserAndSlot(userId, reqVO.getSlotIndex());
            if (occupied != null && !Objects.equals(occupied.getId(), current.getId())) {
                throw exception(VIDEO_WALL_LAYOUT_SLOT_OCCUPIED);
            }
        }
        validateLayout(reqVO);
        VideoWallLayoutDO update = toDataObject(reqVO, userId);
        update.setId(current.getId());
        update.setActive(current.getActive());
        layoutMapper.updateById(update);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void activateLayout(Long id, Long userId) {
        VideoWallLayoutDO layout = validateOwnedLayout(id, userId);
        layoutMapper.deactivateAll(userId);
        VideoWallLayoutDO update = new VideoWallLayoutDO();
        update.setId(layout.getId());
        update.setActive(true);
        layoutMapper.updateById(update);
    }

    @Override
    public void deleteLayout(Long id, Long userId) {
        VideoWallLayoutDO layout = validateOwnedLayout(id, userId);
        layoutMapper.deleteById(layout.getId());
    }

    private void validateLayout(VideoWallLayoutSaveReqVO reqVO) {
        if (reqVO.getNodeId() != null) nodeService.validateNodeAvailable(reqVO.getNodeId());
        if (!SUPPORTED_SPLITS.contains(reqVO.getSplitCount())
                || reqVO.getCameraIds().size() != reqVO.getSplitCount()) {
            throw exception(VIDEO_WALL_LAYOUT_SPLIT_INVALID);
        }
        List<Long> cameraIds = reqVO.getCameraIds().stream().filter(Objects::nonNull).toList();
        if (new HashSet<>(cameraIds).size() != cameraIds.size()) {
            throw exception(VIDEO_WALL_LAYOUT_SPLIT_INVALID);
        }
        if (!cameraIds.isEmpty()) {
            List<CameraDO> cameras = cameraMapper.selectBatchIds(cameraIds);
            if (cameras.size() != cameraIds.size()) {
                throw exception(CAMERA_NOT_FOUND);
            }
        }
    }

    private VideoWallLayoutDO validateOwnedLayout(Long id, Long userId) {
        if (id == null) {
            throw exception(VIDEO_WALL_LAYOUT_NOT_FOUND);
        }
        VideoWallLayoutDO layout = layoutMapper.selectById(id);
        if (layout == null || !Objects.equals(layout.getUserId(), userId)) {
            throw exception(VIDEO_WALL_LAYOUT_NOT_FOUND);
        }
        return layout;
    }

    private static VideoWallLayoutDO toDataObject(VideoWallLayoutSaveReqVO reqVO, Long userId) {
        VideoWallLayoutDO layout = new VideoWallLayoutDO();
        layout.setUserId(userId);
        layout.setSlotIndex(reqVO.getSlotIndex());
        layout.setName(reqVO.getName().trim());
        layout.setSplitCount(reqVO.getSplitCount());
        layout.setNodeId(reqVO.getNodeId());
        layout.setSchemaVersion(SCHEMA_VERSION);
        layout.setCameraIdsJson(JsonUtils.toJsonString(reqVO.getCameraIds()));
        return layout;
    }

    private VideoWallLayoutRespVO convert(VideoWallLayoutDO source) {
        VideoWallLayoutRespVO target = new VideoWallLayoutRespVO();
        target.setId(source.getId());
        target.setSlotIndex(source.getSlotIndex());
        target.setName(source.getName());
        target.setSplitCount(source.getSplitCount());
        target.setNodeId(source.getNodeId());
        target.setSchemaVersion(source.getSchemaVersion());
        List<Long> cameraIds = JsonUtils.parseObjectQuietly(source.getCameraIdsJson(), LONG_LIST);
        target.setCameraIds(cameraIds == null ? List.of() : cameraIds);
        target.setActive(Boolean.TRUE.equals(source.getActive()));
        target.setUpdateTime(source.getUpdateTime());
        return target;
    }

}
