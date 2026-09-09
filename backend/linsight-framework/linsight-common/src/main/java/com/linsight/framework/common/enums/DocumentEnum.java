package com.linsight.framework.common.enums;

import lombok.AllArgsConstructor;
import lombok.Getter;

/**
 * LInsight 本地文档地址。
 */
@Getter
@AllArgsConstructor
public enum DocumentEnum {

    REDIS_INSTALL("http://127.0.0.1:48888/doc.html", "Redis 安装说明"),
    TENANT("http://127.0.0.1:48888/doc.html", "SaaS 多租户说明");

    private final String url;
    private final String memo;

}
