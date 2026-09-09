package com.linsight.module.aivideo.enums.camera;

import lombok.AllArgsConstructor;
import lombok.Getter;

import java.util.Arrays;

@Getter
@AllArgsConstructor
public enum CameraProtocolEnum {

    RTSP("RTSP"),
    ONVIF("ONVIF");

    private final String code;

    public static boolean contains(String code) {
        return Arrays.stream(values()).anyMatch(value -> value.code.equals(code));
    }

}
