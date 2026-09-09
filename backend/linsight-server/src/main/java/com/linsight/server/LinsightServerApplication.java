package com.linsight.server;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * LInsight 平台后端启动类。
 */
@SuppressWarnings("SpringComponentScan") // 忽略 IDEA 无法识别 ${linsight.info.base-package}
@SpringBootApplication(scanBasePackages = {"${linsight.info.base-package}.server", "${linsight.info.base-package}.module"},
        excludeName = {
            // RPC 相关
//            "org.springframework.cloud.openfeign.FeignAutoConfiguration",
//            "com.linsight.module.system.framework.rpc.config.RpcConfiguration"
        })
public class LinsightServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(LinsightServerApplication.class, args);
    }

}
