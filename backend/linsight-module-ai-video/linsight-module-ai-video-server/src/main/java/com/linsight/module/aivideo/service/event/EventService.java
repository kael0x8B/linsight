package com.linsight.module.aivideo.service.event;

import com.linsight.framework.common.pojo.PageResult;
import com.linsight.module.aivideo.controller.admin.event.vo.EventActionReqVO;
import com.linsight.module.aivideo.controller.admin.event.vo.EventPageReqVO;
import com.linsight.module.aivideo.controller.admin.event.vo.EventRespVO;
import com.linsight.module.aivideo.controller.node.event.vo.EventIngestReqVO;
import com.linsight.module.aivideo.controller.node.event.vo.EventTransitionReqVO;
import com.linsight.module.aivideo.dal.dataobject.event.EventDO;
import com.linsight.module.aivideo.dal.dataobject.event.EventOutboxDO;

import java.time.LocalDateTime;
import java.util.List;

public interface EventService {
    PageResult<EventRespVO> getPageView(EventPageReqVO reqVO);
    PageResult<EventDO> getPage(EventPageReqVO reqVO);
    EventRespVO getDetail(Long id);
    Long createEntryAccessEvent(EntryAccessEventDTO event);
    Long ingest(EventIngestReqVO reqVO, Long nodeId);
    Long uploadMedia(Long eventId, Long nodeId, String mediaType, String fileName, String contentType,
                     byte[] content, LocalDateTime captureStartTime, LocalDateTime captureEndTime);
    void applyRuntimeTransition(EventTransitionReqVO reqVO, Long nodeId);
    void assign(Long id, EventActionReqVO reqVO, Long operatorId);
    void handle(Long id, EventActionReqVO reqVO, Long operatorId);
    void close(Long id, EventActionReqVO reqVO, Long operatorId);
    void markFalsePositive(Long id, EventActionReqVO reqVO, Long operatorId);
    List<EventOutboxDO> getReadyOutboxGlobal();
    void dispatchOutbox(Long outboxId);
}
