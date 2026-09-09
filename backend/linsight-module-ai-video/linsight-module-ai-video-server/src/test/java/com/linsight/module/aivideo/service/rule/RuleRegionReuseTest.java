package com.linsight.module.aivideo.service.rule;

import org.junit.jupiter.api.Test;
import java.util.List;
import java.util.Map;
import static org.assertj.core.api.Assertions.assertThat;

class RuleRegionReuseTest {
    @Test void unrestrictedAndFullFrameRulesDoNotNeedCameraSpecificConfirmation() {
        assertThat(rule(List.of()).hasCustomRegions()).isFalse();
        assertThat(rule(List.of(Map.of("points", List.of(point(0,0), point(1,0), point(1,1), point(0,1))))).hasCustomRegions()).isFalse();
    }
    @Test void subregionsAndCrossedPolygonsNeedConfirmation() {
        assertThat(rule(List.of(Map.of("points", List.of(point(0,0), point(.5,0), point(.5,1), point(0,1))))).hasCustomRegions()).isTrue();
        assertThat(rule(List.of(Map.of("points", List.of(point(0,0), point(1,1), point(1,0), point(0,1))))).hasCustomRegions()).isTrue();
    }
    private Map<String, Double> point(double x, double y) { return Map.of("x", x, "y", y); }
    private RuleVersionConfigDTO rule(List<?> regions) { return new RuleVersionConfigDTO(1L, 2L, 1, "SAFETY_HELMET", Map.of("regions", regions)); }
}
