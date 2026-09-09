package com.linsight.module.aivideo.service.node;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;
import org.springframework.validation.annotation.Validated;

@Data
@Component
@Validated
@ConfigurationProperties(prefix = "linsight.ai-video.node-log")
public class NodeLogProperties {
    @Min(1) @Max(365) private int debugRetentionDays = 1;
    @Min(1) @Max(365) private int infoRetentionDays = 3;
    @Min(1) @Max(365) private int warnRetentionDays = 7;
    @Min(1) @Max(365) private int errorRetentionDays = 14;
    @Min(100) @Max(10000) private int cleanupBatchSize = 5000;
    @Min(1) @Max(100) private int cleanupMaxBatches = 10;
}
