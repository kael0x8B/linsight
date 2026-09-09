package com.linsight.module.aivideo.service.integration;

import com.fasterxml.jackson.core.type.TypeReference;
import com.linsight.framework.common.pojo.PageResult;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.framework.common.util.object.BeanUtils;
import com.linsight.module.aivideo.controller.admin.integration.vo.WebhookDeliveryPageReqVO;
import com.linsight.module.aivideo.controller.admin.integration.vo.WebhookDeliveryRespVO;
import com.linsight.module.aivideo.controller.admin.integration.vo.WebhookPageReqVO;
import com.linsight.module.aivideo.controller.admin.integration.vo.WebhookRespVO;
import com.linsight.module.aivideo.controller.admin.integration.vo.WebhookSaveReqVO;
import com.linsight.module.aivideo.controller.admin.integration.vo.WebhookSecretRespVO;
import com.linsight.module.aivideo.dal.dataobject.integration.WebhookDeliveryDO;
import com.linsight.module.aivideo.dal.dataobject.integration.WebhookEndpointDO;
import com.linsight.module.aivideo.dal.mysql.integration.WebhookDeliveryMapper;
import com.linsight.module.aivideo.dal.mysql.integration.WebhookEndpointMapper;
import com.linsight.module.aivideo.framework.security.SensitiveTextRedactor;
import com.linsight.module.aivideo.integration.webhook.WebhookDeliveryClient;
import com.linsight.module.aivideo.integration.webhook.WebhookUrlValidator;
import com.linsight.module.aivideo.service.settings.GlobalSettingsService;
import jakarta.annotation.Resource;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.security.SecureRandom;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static com.linsight.framework.common.exception.util.ServiceExceptionUtil.exception;
import static com.linsight.module.aivideo.enums.integration.ErrorCodeConstants.WEBHOOK_DELIVERY_NOT_FOUND;
import static com.linsight.module.aivideo.enums.integration.ErrorCodeConstants.WEBHOOK_DELIVERY_NOT_REPLAYABLE;
import static com.linsight.module.aivideo.enums.integration.ErrorCodeConstants.WEBHOOK_NOT_FOUND;
import static com.linsight.module.aivideo.enums.integration.ErrorCodeConstants.WEBHOOK_URL_UNSAFE;

@Service
public class WebhookServiceImpl implements WebhookService {
    private static final TypeReference<List<String>> STRING_LIST = new TypeReference<>() { };
    private static final SecureRandom SECURE_RANDOM = new SecureRandom();

    @Resource private WebhookEndpointMapper endpointMapper;
    @Resource private WebhookDeliveryMapper deliveryMapper;
    @Resource private WebhookDeliveryClient deliveryClient;
    @Resource private WebhookUrlValidator urlValidator;
    @Resource private GlobalSettingsService globalSettingsService;

    @Override
    public PageResult<WebhookRespVO> getPage(WebhookPageReqVO reqVO) {
        PageResult<WebhookEndpointDO> page = endpointMapper.selectPage(reqVO, reqVO.getName(), reqVO.getStatus());
        return new PageResult<>(page.getList().stream().map(this::toResponse).toList(), page.getTotal());
    }

    @Override
    public WebhookRespVO get(Long id) {
        return toResponse(requireEndpoint(id));
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public WebhookSecretRespVO create(WebhookSaveReqVO reqVO) {
        validateUrl(reqVO.getUrl());
        String secret = reqVO.getSecret() == null || reqVO.getSecret().isBlank()
                ? generateSecret() : reqVO.getSecret();
        WebhookEndpointDO value = fromRequest(reqVO);
        value.setSecret(secret);
        value.setSuccessCount(0L);
        value.setFailureCount(0L);
        endpointMapper.insert(value);
        return new WebhookSecretRespVO(value.getId(), secret);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void update(WebhookSaveReqVO reqVO) {
        WebhookEndpointDO existing = requireEndpoint(reqVO.getId());
        validateUrl(reqVO.getUrl());
        WebhookEndpointDO value = fromRequest(reqVO);
        if (reqVO.getSecret() == null || reqVO.getSecret().isBlank()) {
            value.setSecret(existing.getSecret());
        } else {
            value.setSecret(reqVO.getSecret());
        }
        endpointMapper.updateById(value);
    }

    @Override
    public void delete(Long id) {
        requireEndpoint(id);
        endpointMapper.deleteById(id);
    }

    @Override
    public void updateStatus(Long id, Integer status) {
        requireEndpoint(id);
        WebhookEndpointDO value = new WebhookEndpointDO();
        value.setId(id);
        value.setStatus(status);
        endpointMapper.updateById(value);
    }

    @Override
    public Long createTestDelivery(Long endpointId) {
        WebhookEndpointDO endpoint = requireEndpoint(endpointId);
        String messageId = UUID.randomUUID().toString();
        String payload = JsonUtils.toJsonString(Map.of(
                "type", "ai-video.event.test",
                "version", "1.0",
                "messageId", messageId,
                "occurredAt", LocalDateTime.now(),
                "data", Map.of("eventType", "TEST", "severity", "INFO",
                        "simulated", true, "endpointId", endpoint.getId())));
        return insertDelivery(endpoint, null, messageId, "TEST", "INFO", payload, true);
    }

    @Override
    public PageResult<WebhookDeliveryRespVO> getDeliveryPage(WebhookDeliveryPageReqVO reqVO) {
        PageResult<WebhookDeliveryDO> page = deliveryMapper.selectPage(reqVO, reqVO.getEndpointId(),
                reqVO.getStatus(), reqVO.getIsTest());
        return new PageResult<>(BeanUtils.toBean(page.getList(), WebhookDeliveryRespVO.class), page.getTotal());
    }

    @Override
    public WebhookDeliveryRespVO getDelivery(Long id) {
        WebhookDeliveryDO value = deliveryMapper.selectById(id);
        if (value == null) throw exception(WEBHOOK_DELIVERY_NOT_FOUND);
        return BeanUtils.toBean(value, WebhookDeliveryRespVO.class);
    }

    @Override
    public void replay(Long deliveryId) {
        WebhookDeliveryDO value = deliveryMapper.selectById(deliveryId);
        if (value == null) throw exception(WEBHOOK_DELIVERY_NOT_FOUND);
        if (!"DEAD".equals(value.getStatus())) throw exception(WEBHOOK_DELIVERY_NOT_REPLAYABLE);
        value.setStatus("PENDING");
        value.setAttempts(0);
        value.setNextAttemptTime(LocalDateTime.now());
        value.setLastError(null);
        value.setResponseStatus(null);
        value.setResponseBody(null);
        deliveryMapper.updateById(value);
    }

    @Override
    public void enqueueEvent(Long eventId, String payload) {
        if (!globalSettingsService.getCurrent().getSettings().getNotificationsEnabled()) return;
        Map<String, Object> envelope = JsonUtils.parseMap(payload);
        if (envelope == null) return;
        Map<String, Object> data = asMap(envelope.get("data"));
        String messageId = stringValue(envelope.get("messageId"));
        String eventType = stringValue(data.get("eventType"));
        String severity = stringValue(data.get("severity"));
        if (messageId == null || eventType == null) return;
        for (WebhookEndpointDO endpoint : endpointMapper.selectEnabled()) {
            if (!matches(parseList(endpoint.getEventTypesJson()), eventType)
                    || !matches(parseList(endpoint.getSeveritiesJson()), severity)) {
                continue;
            }
            try {
                insertDelivery(endpoint, eventId, messageId, eventType, severity, payload, false);
            } catch (DuplicateKeyException ignored) {
                // Outbox retry is idempotent for tenant/endpoint/messageId.
            }
        }
    }

    @Override
    public List<WebhookDeliveryDO> getReadyDeliveriesGlobal() {
        return deliveryMapper.selectReadyGlobal();
    }

    @Override
    public void deliver(Long deliveryId) {
        WebhookDeliveryDO delivery = deliveryMapper.selectById(deliveryId);
        if (delivery == null || !("PENDING".equals(delivery.getStatus())
                || "RETRY".equals(delivery.getStatus()))) return;
        WebhookEndpointDO endpoint = endpointMapper.selectById(delivery.getEndpointId());
        if (endpoint == null || endpoint.getStatus() != 0) {
            markDead(delivery, "ENDPOINT_DISABLED_OR_DELETED", null, null, 0);
            return;
        }
        WebhookDeliveryClient.Result result = deliveryClient.deliver(endpoint,
                delivery.getPayload(), delivery.getIdempotencyKey());
        int attempts = delivery.getAttempts() + 1;
        delivery.setAttempts(attempts);
        delivery.setLastAttemptTime(LocalDateTime.now());
        delivery.setResponseStatus(result.getStatusCode());
        delivery.setResponseBody(limit(SensitiveTextRedactor.redactText(result.getResponseBody()), 2000));
        delivery.setDurationMs(result.getDurationMs());
        delivery.setLastError(limit(result.getError(), 500));
        if (result.isSuccess()) {
            delivery.setStatus("SUCCEEDED");
            delivery.setNextAttemptTime(LocalDateTime.now());
            delivery.setLastError(null);
            endpointMapper.recordSuccess(endpoint.getId());
        } else if (attempts >= endpoint.getMaxAttempts()) {
            delivery.setStatus("DEAD");
            endpointMapper.recordFailure(endpoint.getId(), delivery.getLastError());
        } else {
            delivery.setStatus("RETRY");
            delivery.setNextAttemptTime(LocalDateTime.now().plusSeconds(backoffSeconds(attempts)));
        }
        deliveryMapper.updateById(delivery);
    }

    private Long insertDelivery(WebhookEndpointDO endpoint, Long eventId, String messageId,
                                String eventType, String severity, String payload, boolean test) {
        WebhookDeliveryDO delivery = new WebhookDeliveryDO();
        delivery.setEndpointId(endpoint.getId());
        delivery.setEventId(eventId);
        delivery.setMessageId(messageId);
        delivery.setIdempotencyKey(eventId == null ? "test:" + messageId : "event:" + eventId);
        delivery.setEventType(eventType);
        delivery.setSeverity(severity);
        delivery.setPayload(payload);
        delivery.setStatus("PENDING");
        delivery.setAttempts(0);
        delivery.setNextAttemptTime(LocalDateTime.now());
        delivery.setIsTest(test);
        deliveryMapper.insert(delivery);
        return delivery.getId();
    }

    private void markDead(WebhookDeliveryDO delivery, String error, Integer status,
                          String response, int durationMs) {
        delivery.setStatus("DEAD");
        delivery.setAttempts(delivery.getAttempts() + 1);
        delivery.setLastAttemptTime(LocalDateTime.now());
        delivery.setResponseStatus(status);
        delivery.setResponseBody(limit(SensitiveTextRedactor.redactText(response), 2000));
        delivery.setDurationMs(durationMs);
        delivery.setLastError(error);
        deliveryMapper.updateById(delivery);
        if (endpointMapper.selectById(delivery.getEndpointId()) != null) {
            endpointMapper.recordFailure(delivery.getEndpointId(), error);
        }
    }

    private WebhookEndpointDO requireEndpoint(Long id) {
        WebhookEndpointDO value = id == null ? null : endpointMapper.selectById(id);
        if (value == null) throw exception(WEBHOOK_NOT_FOUND);
        return value;
    }

    private void validateUrl(String url) {
        if (!urlValidator.isSafe(url)) throw exception(WEBHOOK_URL_UNSAFE);
    }

    private WebhookEndpointDO fromRequest(WebhookSaveReqVO reqVO) {
        WebhookEndpointDO value = BeanUtils.toBean(reqVO, WebhookEndpointDO.class);
        value.setEventTypesJson(JsonUtils.toJsonString(clean(reqVO.getEventTypes())));
        value.setSeveritiesJson(JsonUtils.toJsonString(clean(reqVO.getSeverities())));
        return value;
    }

    private WebhookRespVO toResponse(WebhookEndpointDO value) {
        WebhookRespVO result = BeanUtils.toBean(value, WebhookRespVO.class);
        result.setSecretMasked("********");
        result.setEventTypes(parseList(value.getEventTypesJson()));
        result.setSeverities(parseList(value.getSeveritiesJson()));
        long success = value.getSuccessCount() == null ? 0 : value.getSuccessCount();
        long failure = value.getFailureCount() == null ? 0 : value.getFailureCount();
        result.setSuccessRate(success + failure == 0 ? null
                : Math.round(success * 10000.0 / (success + failure)) / 100.0);
        return result;
    }

    private static List<String> clean(List<String> values) {
        if (values == null) return List.of();
        return new ArrayList<>(values.stream().filter(value -> value != null && !value.isBlank())
                .map(String::trim).distinct().toList());
    }

    private static List<String> parseList(String json) {
        if (json == null || json.isBlank()) return List.of();
        List<String> values = JsonUtils.parseObjectQuietly(json, STRING_LIST);
        return values == null ? List.of() : values;
    }

    private static boolean matches(List<String> filter, String value) {
        return filter.isEmpty() || (value != null && filter.contains(value));
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> asMap(Object value) {
        return value instanceof Map<?, ?> map ? (Map<String, Object>) map : Map.of();
    }

    private static String stringValue(Object value) {
        return value == null ? null : String.valueOf(value);
    }

    private static long backoffSeconds(int attempts) {
        return Math.min(3600, 5L * (1L << Math.min(attempts - 1, 9)));
    }

    private static String generateSecret() {
        byte[] value = new byte[32];
        SECURE_RANDOM.nextBytes(value);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(value);
    }

    private static String limit(String value, int max) {
        if (value == null) return null;
        return value.length() <= max ? value : value.substring(0, max);
    }
}
