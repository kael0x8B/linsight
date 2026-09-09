package com.linsight.module.aivideo.dal.mysql.event;

import com.baomidou.mybatisplus.annotation.InterceptorIgnore;
import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.module.aivideo.dal.dataobject.event.EventOutboxDO;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface EventOutboxMapper extends BaseMapperX<EventOutboxDO> {
    @InterceptorIgnore(tenantLine = "true")
    @Select("""
            SELECT * FROM ai_event_outbox
            WHERE deleted = b'0' AND status = 'PENDING' AND next_attempt_time <= CURRENT_TIMESTAMP
            ORDER BY id LIMIT 100
            """)
    List<EventOutboxDO> selectReadyGlobal();
}
