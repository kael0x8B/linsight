package com.linsight.module.aivideo.dal.mysql.camera;

import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.linsight.module.aivideo.dal.dataobject.camera.CameraStreamCheckDO;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface CameraStreamCheckMapper extends BaseMapperX<CameraStreamCheckDO> {

    default CameraStreamCheckDO selectFirstQueued(Long nodeId) {
        return selectOne(new LambdaQueryWrapperX<CameraStreamCheckDO>()
                .eq(CameraStreamCheckDO::getNodeId, nodeId)
                .eq(CameraStreamCheckDO::getStatus, "QUEUED")
                .orderByAsc(CameraStreamCheckDO::getId)
                .last("LIMIT 1"));
    }

    default int claim(Long id) {
        CameraStreamCheckDO update = new CameraStreamCheckDO();
        update.setId(id);
        update.setStatus("RUNNING");
        update.setStartTime(java.time.LocalDateTime.now());
        update.setUpdater("edge-agent");
        return update(update, new LambdaUpdateWrapper<CameraStreamCheckDO>()
                .eq(CameraStreamCheckDO::getId, id)
                .eq(CameraStreamCheckDO::getStatus, "QUEUED"));
    }

}
