package com.linsight.module.aivideo.job;

import com.linsight.framework.tenant.core.util.TenantUtils;
import com.linsight.module.aivideo.service.event.EventService;
import jakarta.annotation.Resource;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class EventOutboxDispatchJob {
    @Resource private EventService eventService;

    @Scheduled(fixedDelay = 2000)
    public void dispatch() {
        eventService.getReadyOutboxGlobal().forEach(outbox ->
                TenantUtils.execute(outbox.getTenantId(), () -> eventService.dispatchOutbox(outbox.getId())));
    }
}
