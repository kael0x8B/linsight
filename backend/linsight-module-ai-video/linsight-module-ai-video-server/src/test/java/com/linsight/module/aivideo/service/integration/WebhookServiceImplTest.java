package com.linsight.module.aivideo.service.integration;

import com.linsight.module.aivideo.dal.dataobject.integration.WebhookDeliveryDO;
import com.linsight.module.aivideo.dal.dataobject.integration.WebhookEndpointDO;
import com.linsight.module.aivideo.dal.mysql.integration.WebhookDeliveryMapper;
import com.linsight.module.aivideo.dal.mysql.integration.WebhookEndpointMapper;
import com.linsight.module.aivideo.integration.webhook.WebhookDeliveryClient;
import com.linsight.module.aivideo.integration.webhook.WebhookUrlValidator;
import com.linsight.module.aivideo.service.settings.GlobalSettingsService;
import com.linsight.module.aivideo.controller.admin.settings.vo.AiGlobalSettingsVO;
import com.linsight.module.aivideo.controller.admin.settings.vo.GlobalSettingsRespVO;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class WebhookServiceImplTest {
    private WebhookEndpointMapper endpointMapper;
    private WebhookDeliveryMapper deliveryMapper;
    private WebhookDeliveryClient deliveryClient;
    private WebhookServiceImpl service;

    @BeforeEach
    void setUp() {
        endpointMapper = mock(WebhookEndpointMapper.class);
        deliveryMapper = mock(WebhookDeliveryMapper.class);
        deliveryClient = mock(WebhookDeliveryClient.class);
        service = new WebhookServiceImpl();
        ReflectionTestUtils.setField(service, "endpointMapper", endpointMapper);
        ReflectionTestUtils.setField(service, "deliveryMapper", deliveryMapper);
        ReflectionTestUtils.setField(service, "deliveryClient", deliveryClient);
        ReflectionTestUtils.setField(service, "urlValidator", mock(WebhookUrlValidator.class));
        GlobalSettingsService settingsService = mock(GlobalSettingsService.class);
        AiGlobalSettingsVO settings = new AiGlobalSettingsVO();
        settings.setNotificationsEnabled(true);
        when(settingsService.getCurrent()).thenReturn(new GlobalSettingsRespVO(0, settings));
        ReflectionTestUtils.setField(service, "globalSettingsService", settingsService);
    }

    @Test
    void enqueueEventShouldRespectEndpointFiltersAndKeepPayloadExact() {
        WebhookEndpointDO matched = endpoint(10L);
        matched.setEventTypesJson("[\"AREA_INTRUSION\"]");
        matched.setSeveritiesJson("[\"CRITICAL\"]");
        WebhookEndpointDO ignored = endpoint(11L);
        ignored.setEventTypesJson("[\"FIRE_SMOKE\"]");
        when(endpointMapper.selectEnabled()).thenReturn(List.of(matched, ignored));
        String payload = "{\"type\":\"ai-video.event.changed\",\"messageId\":\"m-1\","
                + "\"data\":{\"eventType\":\"AREA_INTRUSION\",\"severity\":\"CRITICAL\"}}";

        service.enqueueEvent(42L, payload);

        ArgumentCaptor<WebhookDeliveryDO> captor = ArgumentCaptor.forClass(WebhookDeliveryDO.class);
        verify(deliveryMapper).insert(captor.capture());
        assertThat(captor.getValue().getEndpointId()).isEqualTo(10L);
        assertThat(captor.getValue().getIdempotencyKey()).isEqualTo("event:42");
        assertThat(captor.getValue().getPayload()).isEqualTo(payload);
    }

    @Test
    void exhaustedRetryShouldBecomeDeadLetter() {
        WebhookEndpointDO endpoint = endpoint(10L);
        endpoint.setMaxAttempts(2);
        WebhookDeliveryDO delivery = new WebhookDeliveryDO();
        delivery.setId(20L);
        delivery.setEndpointId(10L);
        delivery.setPayload("{}");
        delivery.setIdempotencyKey("event:42");
        delivery.setStatus("RETRY");
        delivery.setAttempts(1);
        when(deliveryMapper.selectById(20L)).thenReturn(delivery);
        when(endpointMapper.selectById(10L)).thenReturn(endpoint);
        when(deliveryClient.deliver(any(), any(), any())).thenReturn(
                new WebhookDeliveryClient.Result(false, 503, "token=secret", 18, "HTTP_503"));

        service.deliver(20L);

        assertThat(delivery.getStatus()).isEqualTo("DEAD");
        assertThat(delivery.getAttempts()).isEqualTo(2);
        assertThat(delivery.getResponseBody()).doesNotContain("secret");
        verify(endpointMapper).recordFailure(10L, "HTTP_503");
        verify(deliveryMapper).updateById(delivery);
    }

    private static WebhookEndpointDO endpoint(Long id) {
        WebhookEndpointDO value = new WebhookEndpointDO();
        value.setId(id);
        value.setStatus(0);
        value.setMaxAttempts(5);
        value.setTimeoutMs(5000);
        value.setSecret("01234567890123456789012345678901");
        value.setEventTypesJson("[]");
        value.setSeveritiesJson("[]");
        return value;
    }
}
