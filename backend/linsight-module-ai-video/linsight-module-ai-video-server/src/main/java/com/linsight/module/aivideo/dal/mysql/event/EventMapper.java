package com.linsight.module.aivideo.dal.mysql.event;

import com.linsight.framework.common.pojo.PageResult;
import com.linsight.framework.common.pojo.PageParam;
import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.linsight.module.aivideo.dal.dataobject.event.EventDO;
import com.baomidou.mybatisplus.core.conditions.update.LambdaUpdateWrapper;
import org.apache.ibatis.annotations.Mapper;

import java.time.LocalDateTime;

@Mapper
public interface EventMapper extends BaseMapperX<EventDO> {
    default EventDO selectBySourceEventId(String sourceEventId) {
        return selectOne(EventDO::getSourceEventId, sourceEventId);
    }

    default PageResult<EventDO> selectPage(PageParam pageParam, String eventNo, Long taskId, Long algorithmId, Long cameraId,
                                            String eventType, String severity, String status,
                                            java.time.LocalDateTime[] occurredTime) {
        return selectPage(pageParam, new LambdaQueryWrapperX<EventDO>()
                .likeIfPresent(EventDO::getEventNo, eventNo)
                .eqIfPresent(EventDO::getTaskId, taskId)
                .eqIfPresent(EventDO::getAlgorithmId, algorithmId)
                .eqIfPresent(EventDO::getCameraId, cameraId)
                .eqIfPresent(EventDO::getEventType, eventType)
                .eqIfPresent(EventDO::getSeverity, severity)
                .eqIfPresent(EventDO::getStatus, status)
                .betweenIfPresent(EventDO::getOccurredTime, occurredTime)
                .orderByDesc(EventDO::getOccurredTime));
    }

    /**
     * Updates operator-controlled state with an explicit version predicate.
     *
     * <p>The MPJ mapper bridge does not populate MyBatis-Plus' synthetic optimistic-lock
     * parameter for {@code updateById}; using an explicit wrapper keeps the version check
     * atomic and also lets runtime transitions clear nullable fields.</p>
     */
    default int updateMutableState(EventDO event) {
        Integer version = event.getVersion();
        LocalDateTime updateTime = LocalDateTime.now();
        LambdaUpdateWrapper<EventDO> update = new LambdaUpdateWrapper<EventDO>()
                .eq(EventDO::getId, event.getId())
                .eq(EventDO::getVersion, version)
                .set(EventDO::getStatus, event.getStatus())
                .set(EventDO::getEvidenceStatus, event.getEvidenceStatus())
                .set(EventDO::getActiveDedupKey, event.getActiveDedupKey())
                .set(EventDO::getCloseTime, event.getCloseTime())
                .set(EventDO::getAssigneeId, event.getAssigneeId())
                .set(EventDO::getHandlingResult, event.getHandlingResult())
                .set(EventDO::getFalsePositiveReason, event.getFalsePositiveReason())
                .set(EventDO::getVersion, version + 1)
                .set(EventDO::getUpdateTime, updateTime)
                .set(EventDO::getUpdater, event.getUpdater());
        int rows = update(null, update);
        if (rows == 1) {
            event.setVersion(version + 1);
            event.setUpdateTime(updateTime);
        }
        return rows;
    }
}
