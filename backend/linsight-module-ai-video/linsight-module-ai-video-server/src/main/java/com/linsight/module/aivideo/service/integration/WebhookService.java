package com.linsight.module.aivideo.service.integration;

import com.linsight.framework.common.pojo.PageResult;
import com.linsight.module.aivideo.controller.admin.integration.vo.WebhookDeliveryPageReqVO;
import com.linsight.module.aivideo.controller.admin.integration.vo.WebhookDeliveryRespVO;
import com.linsight.module.aivideo.controller.admin.integration.vo.WebhookPageReqVO;
import com.linsight.module.aivideo.controller.admin.integration.vo.WebhookRespVO;
import com.linsight.module.aivideo.controller.admin.integration.vo.WebhookSaveReqVO;
import com.linsight.module.aivideo.controller.admin.integration.vo.WebhookSecretRespVO;
import com.linsight.module.aivideo.dal.dataobject.integration.WebhookDeliveryDO;

import java.util.List;

public interface WebhookService {
    PageResult<WebhookRespVO> getPage(WebhookPageReqVO reqVO);
    WebhookRespVO get(Long id);
    WebhookSecretRespVO create(WebhookSaveReqVO reqVO);
    void update(WebhookSaveReqVO reqVO);
    void delete(Long id);
    void updateStatus(Long id, Integer status);
    Long createTestDelivery(Long endpointId);
    PageResult<WebhookDeliveryRespVO> getDeliveryPage(WebhookDeliveryPageReqVO reqVO);
    WebhookDeliveryRespVO getDelivery(Long id);
    void replay(Long deliveryId);
    void enqueueEvent(Long eventId, String payload);
    List<WebhookDeliveryDO> getReadyDeliveriesGlobal();
    void deliver(Long deliveryId);
}
