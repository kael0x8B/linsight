package com.linsight.module.aivideo.dal.mysql.camera;

import com.linsight.framework.common.pojo.PageResult;
import com.linsight.framework.common.pojo.PageParam;
import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.linsight.module.aivideo.dal.dataobject.camera.CameraDO;
import org.apache.ibatis.annotations.Mapper;

import java.time.LocalDateTime;

@Mapper
public interface CameraMapper extends BaseMapperX<CameraDO> {

    default CameraDO selectByCode(String code) {
        return selectOne(CameraDO::getCode, code);
    }

    default PageResult<CameraDO> selectPage(PageParam pageParam, String name, String code, Long groupId,
                                            String protocol, Integer onlineStatus, Integer status) {
        return selectPage(pageParam, new LambdaQueryWrapperX<CameraDO>()
                .likeIfPresent(CameraDO::getName, name)
                .likeIfPresent(CameraDO::getCode, code)
                .eqIfPresent(CameraDO::getGroupId, groupId)
                .eqIfPresent(CameraDO::getProtocol, protocol)
                .eqIfPresent(CameraDO::getOnlineStatus, onlineStatus)
                .eqIfPresent(CameraDO::getStatus, status)
                .orderByDesc(CameraDO::getId));
    }

    default int updateStreamCheckStatus(Long id, Integer onlineStatus, LocalDateTime checkTime,
                                        String errorCode, String errorMessage) {
        com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper<CameraDO> update =
                new com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper<CameraDO>()
                        .eq(CameraDO::getId, id)
                        .set(CameraDO::getOnlineStatus, onlineStatus)
                        .set(CameraDO::getLastCheckTime, checkTime)
                        .set(CameraDO::getLastErrorCode, errorCode)
                        .set(CameraDO::getLastErrorMessage, errorMessage);
        if (onlineStatus == 1) {
            update.set(CameraDO::getLastOnlineTime, checkTime);
        }
        return update(null, update);
    }

}
