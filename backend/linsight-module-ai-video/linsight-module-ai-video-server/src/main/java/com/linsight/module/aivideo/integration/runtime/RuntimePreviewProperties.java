package com.linsight.module.aivideo.integration.runtime;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import java.time.Duration;

@Data
@Component
@ConfigurationProperties(prefix = "linsight.ai-video.runtime")
public class RuntimePreviewProperties {

    private boolean enabled;
    private String baseUrl = "http://127.0.0.1:48900";
    private String apiKey;
    private Duration connectTimeout = Duration.ofSeconds(2);
    private Duration readTimeout = Duration.ofSeconds(12);

}
