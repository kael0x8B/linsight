package com.linsight.module.aivideo.convert.event;

import com.linsight.framework.common.pojo.PageResult;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.module.aivideo.controller.admin.event.vo.EventActionRespVO;
import com.linsight.module.aivideo.controller.admin.event.vo.EventMediaRespVO;
import com.linsight.module.aivideo.controller.admin.event.vo.EventRespVO;
import com.linsight.module.aivideo.dal.dataobject.event.EventActionDO;
import com.linsight.module.aivideo.dal.dataobject.event.EventDO;
import com.linsight.module.aivideo.dal.dataobject.event.EventMediaDO;
import org.springframework.beans.BeanUtils;

import java.util.List;

public final class EventConvert {
    private EventConvert() {}

    public static EventRespVO convert(EventDO source) {
        EventRespVO target = new EventRespVO();
        BeanUtils.copyProperties(source, target);
        target.setObjectSnapshot(JsonUtils.parseMap(source.getObjectSnapshot()));
        target.setTaskSnapshot(JsonUtils.parseMap(source.getTaskSnapshot()));
        target.setPipelineSnapshot(JsonUtils.parseMap(source.getPipelineSnapshot()));
        target.setModelSnapshot(JsonUtils.parseMap(source.getModelSnapshot()));
        target.setRuleSnapshot(JsonUtils.parseMap(source.getRuleSnapshot()));
        return target;
    }

    public static PageResult<EventRespVO> convertPage(PageResult<EventDO> source) {
        return new PageResult<>(source.getList().stream().map(EventConvert::convert).toList(), source.getTotal());
    }

    public static List<EventMediaRespVO> convertMedia(List<EventMediaDO> source) {
        return source.stream().map(value -> {
            EventMediaRespVO target = new EventMediaRespVO();
            BeanUtils.copyProperties(value, target);
            return target;
        }).toList();
    }

    public static List<EventActionRespVO> convertActions(List<EventActionDO> source) {
        return source.stream().map(value -> {
            EventActionRespVO target = new EventActionRespVO();
            BeanUtils.copyProperties(value, target);
            return target;
        }).toList();
    }
}
