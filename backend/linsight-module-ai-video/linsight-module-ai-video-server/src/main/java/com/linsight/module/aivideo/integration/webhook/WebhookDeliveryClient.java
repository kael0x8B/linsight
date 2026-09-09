package com.linsight.module.aivideo.integration.webhook;

import com.linsight.module.aivideo.dal.dataobject.integration.WebhookEndpointDO;
import lombok.AllArgsConstructor;
import lombok.Data;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.client.RestTemplate;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.HexFormat;
import java.util.List;
import java.util.UUID;

@Component
public class WebhookDeliveryClient {
    private final WebhookUrlValidator urlValidator;

    public WebhookDeliveryClient(WebhookUrlValidator urlValidator) {
        this.urlValidator = urlValidator;
    }

    public Result deliver(WebhookEndpointDO endpoint, String payload, String idempotencyKey) {
        if (!urlValidator.isSafe(endpoint.getUrl())) {
            return new Result(false, null, null, 0, "UNSAFE_WEBHOOK_URL");
        }
        long started = System.nanoTime();
        String timestamp = String.valueOf(Instant.now().getEpochSecond());
        String nonce = UUID.randomUUID().toString();
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.setAccept(List.of(MediaType.APPLICATION_JSON));
        headers.set("X-LInsight-Timestamp", timestamp);
        headers.set("X-LInsight-Nonce", nonce);
        headers.set("X-LInsight-Signature", "v1=" + sign(endpoint.getSecret(), timestamp, nonce, payload));
        headers.set("X-LInsight-Event-Id", idempotencyKey);

        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(endpoint.getTimeoutMs());
        factory.setReadTimeout(endpoint.getTimeoutMs());
        RestTemplate restTemplate = new RestTemplate(factory);
        try {
            var response = restTemplate.exchange(endpoint.getUrl(), HttpMethod.POST,
                    new HttpEntity<>(payload, headers), String.class);
            int duration = elapsedMs(started);
            return new Result(response.getStatusCode().is2xxSuccessful(), response.getStatusCode().value(),
                    response.getBody(), duration, response.getStatusCode().is2xxSuccessful()
                    ? null : "HTTP_" + response.getStatusCode().value());
        } catch (RestClientResponseException error) {
            return new Result(false, error.getStatusCode().value(), error.getResponseBodyAsString(),
                    elapsedMs(started), "HTTP_" + error.getStatusCode().value());
        } catch (ResourceAccessException error) {
            return new Result(false, null, null, elapsedMs(started), "NETWORK_OR_TIMEOUT");
        }
    }

    static String sign(String secret, String timestamp, String nonce, String payload) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            byte[] digest = mac.doFinal((timestamp + "." + nonce + "." + payload)
                    .getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (java.security.GeneralSecurityException error) {
            throw new IllegalStateException("HMAC-SHA256 unavailable", error);
        }
    }

    private static int elapsedMs(long started) {
        return (int) Math.min(Integer.MAX_VALUE, (System.nanoTime() - started) / 1_000_000L);
    }

    @Data
    @AllArgsConstructor
    public static class Result {
        private boolean success;
        private Integer statusCode;
        private String responseBody;
        private int durationMs;
        private String error;
    }
}
