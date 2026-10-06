package com.linsight.module.aivideo.integration.release;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class NodeApplicationReleaseConfiguration {
    // Preserve the default scheduler for other @Scheduled jobs when Boot backs off
    // because this configuration provides an explicit lease scheduler.
    @Bean("taskScheduler")
    @org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean(name="taskScheduler")
    public org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler defaultScheduler() {
        var scheduler = new org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("scheduling-");
        return scheduler;
    }

    @Bean("nodeApplicationReleaseScheduler")
    public org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler scheduler() {
        var scheduler = new org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("node-release-lease-");
        return scheduler;
    }

    @Bean("nodeApplicationReleaseExecutor")
    public ThreadPoolTaskExecutor executor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1); executor.setMaxPoolSize(1); executor.setQueueCapacity(1);
        executor.setThreadNamePrefix("node-release-");
        executor.setWaitForTasksToCompleteOnShutdown(false);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }
}
