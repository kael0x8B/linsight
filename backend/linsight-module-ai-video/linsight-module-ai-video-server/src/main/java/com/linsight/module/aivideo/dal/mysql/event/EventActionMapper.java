package com.linsight.module.aivideo.dal.mysql.event;

import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.linsight.module.aivideo.dal.dataobject.event.EventActionDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.List;

@Mapper
public interface EventActionMapper extends BaseMapperX<EventActionDO> {
    default List<EventActionDO> selectByEventId(Long eventId) {
        return selectList(new LambdaQueryWrapperX<EventActionDO>()
                .eq(EventActionDO::getEventId, eventId).orderByAsc(EventActionDO::getId));
    }
}
