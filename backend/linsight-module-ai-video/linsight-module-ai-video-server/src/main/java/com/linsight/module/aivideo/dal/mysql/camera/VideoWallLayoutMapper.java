package com.linsight.module.aivideo.dal.mysql.camera;

import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.linsight.module.aivideo.dal.dataobject.camera.VideoWallLayoutDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

@Mapper
public interface VideoWallLayoutMapper extends BaseMapperX<VideoWallLayoutDO> {

    default List<VideoWallLayoutDO> selectListByUserId(Long userId) {
        return selectList(new LambdaQueryWrapperX<VideoWallLayoutDO>()
                .eq(VideoWallLayoutDO::getUserId, userId)
                .orderByAsc(VideoWallLayoutDO::getSlotIndex));
    }

    default VideoWallLayoutDO selectByUserAndSlot(Long userId, Integer slotIndex) {
        return selectOne(new LambdaQueryWrapperX<VideoWallLayoutDO>()
                .eq(VideoWallLayoutDO::getUserId, userId)
                .eq(VideoWallLayoutDO::getSlotIndex, slotIndex));
    }

    default void deactivateAll(Long userId) {
        update(null, new LambdaUpdateWrapper<VideoWallLayoutDO>()
                .eq(VideoWallLayoutDO::getUserId, userId)
                .eq(VideoWallLayoutDO::getActive, true)
                .set(VideoWallLayoutDO::getActive, false));
    }

}
