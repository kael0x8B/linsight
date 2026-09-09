package com.linsight.module.aivideo.controller.admin.rule.vo;

import lombok.AllArgsConstructor;
import lombok.Data;

import java.util.List;

@Data
@AllArgsConstructor
public class RuleDryRunRespVO {
    private boolean matched;
    private Long confirmedAtMillis;
    private List<FrameResult> frames;

    @Data
    @AllArgsConstructor
    public static class FrameResult {
        private Long timestampMillis;
        private boolean roiMatched;
        private int matchedFrames;
        private String state;
    }
}
