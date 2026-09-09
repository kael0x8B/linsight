package com.linsight.module.aivideo.dal.mysql.event;

import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.linsight.module.aivideo.dal.dataobject.event.EventMediaDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

@Mapper
public interface EventMediaMapper extends BaseMapperX<EventMediaDO> {
    default List<EventMediaDO> selectSnapshotsByEventIds(java.util.Collection<Long> ids) {
        if (ids == null || ids.isEmpty()) return List.of();
        return selectList(new LambdaQueryWrapperX<EventMediaDO>().in(EventMediaDO::getEventId, ids)
                .eq(EventMediaDO::getMediaType, "SNAPSHOT").eq(EventMediaDO::getStatus, "READY")
                .orderByAsc(EventMediaDO::getId));
    }

    default List<EventMediaDO> selectByEventId(Long eventId) {
        return selectList(new LambdaQueryWrapperX<EventMediaDO>()
                .eq(EventMediaDO::getEventId, eventId).orderByAsc(EventMediaDO::getId));
    }
}
