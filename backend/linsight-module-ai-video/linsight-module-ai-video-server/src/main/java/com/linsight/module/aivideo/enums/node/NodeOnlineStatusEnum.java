package com.linsight.module.aivideo.enums.node;

import lombok.AllArgsConstructor;
import lombok.Getter;

@Getter
@AllArgsConstructor
public enum NodeOnlineStatusEnum {

    UNKNOWN(0),
    ONLINE(1),
    OFFLINE(2);

    private final Integer status;

}
