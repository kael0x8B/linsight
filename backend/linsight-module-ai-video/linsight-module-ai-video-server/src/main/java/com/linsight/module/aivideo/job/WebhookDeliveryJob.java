package com.linsight.module.aivideo.job;

import com.linsight.framework.tenant.core.util.TenantUtils;
import com.linsight.module.aivideo.service.integration.WebhookService;
import jakarta.annotation.Resource;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class WebhookDeliveryJob {
    @Resource private WebhookService webhookService;

    @Scheduled(fixedDelay = 2000)
    public void dispatch() {
        webhookService.getReadyDeliveriesGlobal().forEach(delivery ->
                TenantUtils.execute(delivery.getTenantId(), () -> webhookService.deliver(delivery.getId())));
    }
}
