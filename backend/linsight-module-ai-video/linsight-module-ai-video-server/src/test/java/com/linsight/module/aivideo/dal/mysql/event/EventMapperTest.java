package com.linsight.module.aivideo.dal.mysql.event;

import com.baomidou.mybatisplus.core.MybatisConfiguration;
import com.baomidou.mybatisplus.core.conditions.Wrapper;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import com.baomidou.mybatisplus.core.metadata.TableInfoHelper;
import com.linsight.module.aivideo.dal.dataobject.event.EventDO;
import org.apache.ibatis.builder.MapperBuilderAssistant;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.CALLS_REAL_METHODS;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

class EventMapperTest {

    @BeforeAll
    static void initializeTableMetadata() {
        TableInfoHelper.initTableInfo(
                new MapperBuilderAssistant(new MybatisConfiguration(), "event-mapper-test"),
                EventDO.class);
    }

    @Test
    @SuppressWarnings("unchecked")
    void mutableStateUpdateMustClearNullableFieldsAndCheckVersion() {
        EventMapper mapper = mock(EventMapper.class, CALLS_REAL_METHODS);
        EventDO event = new EventDO();
        event.setId(1L);
        event.setVersion(3);
        event.setStatus("CLOSED");
        event.setActiveDedupKey(null);
        event.setCloseTime(null);
        event.setUpdater("edge-agent");

        mapper.updateMutableState(event);

        ArgumentCaptor<Wrapper<EventDO>> wrapperCaptor = ArgumentCaptor.forClass(Wrapper.class);
        verify(mapper).update(isNull(), wrapperCaptor.capture());
        LambdaUpdateWrapper<EventDO> wrapper = (LambdaUpdateWrapper<EventDO>) wrapperCaptor.getValue();
        String sqlSet = wrapper.getSqlSet();
        assertTrue(sqlSet.contains("active_dedup_key"));
        assertTrue(sqlSet.contains("close_time"));
        assertTrue(sqlSet.contains("version"));
        assertTrue(wrapper.getSqlSegment().contains("version"));
    }
}
