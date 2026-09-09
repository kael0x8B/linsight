package com.linsight.module.aivideo.integration.webhook;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class WebhookDeliveryClientTest {
    @Test
    void signatureShouldBindTimestampNonceAndExactPayload() {
        String value = WebhookDeliveryClient.sign("01234567890123456789012345678901",
                "1700000000", "nonce-1", "{\"eventId\":42}");

        assertThat(value).hasSize(64)
                .isEqualTo(WebhookDeliveryClient.sign("01234567890123456789012345678901",
                        "1700000000", "nonce-1", "{\"eventId\":42}"))
                .isNotEqualTo(WebhookDeliveryClient.sign("01234567890123456789012345678901",
                        "1700000000", "nonce-2", "{\"eventId\":42}"));
    }

    @Test
    void urlValidatorShouldRejectLoopbackAndNonHttpsTargets() {
        WebhookUrlValidator validator = new WebhookUrlValidator();
        assertThat(validator.isSafe("http://example.com/hook")).isFalse();
        assertThat(validator.isSafe("https://127.0.0.1/hook")).isFalse();
        assertThat(validator.isSafe("https://user:pass@example.com/hook")).isFalse();
    }
}
