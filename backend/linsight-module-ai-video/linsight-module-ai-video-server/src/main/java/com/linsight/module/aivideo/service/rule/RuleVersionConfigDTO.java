package com.linsight.module.aivideo.service.rule;

import lombok.AllArgsConstructor;
import lombok.Data;

import java.util.Map;

@Data
@AllArgsConstructor
public class RuleVersionConfigDTO {
    private Long ruleId;
    private Long versionId;
    private Integer version;
    private String eventType;
    private Map<String, Object> ast;

    /** Full-frame rectangles are camera-independent; other regions need a view-specific check. */
    public boolean hasCustomRegions() {
        Object value = ast.get("regions");
        if (!(value instanceof java.util.List<?> regions)) return false;
        return regions.stream().anyMatch(region -> !isFullFrame(region));
    }

    private static boolean isFullFrame(Object value) {
        if (!(value instanceof Map<?, ?> region) || !(region.get("points") instanceof java.util.List<?> points)
                || points.size() != 4) return false;
        double[][] vertices = new double[4][2];
        java.util.Set<String> corners = new java.util.HashSet<>();
        for (int i = 0; i < 4; i++) {
            if (!(points.get(i) instanceof Map<?, ?> point) || !(point.get("x") instanceof Number x)
                    || !(point.get("y") instanceof Number y)) return false;
            double px = x.doubleValue(), py = y.doubleValue();
            if ((px != 0 && px != 1) || (py != 0 && py != 1)) return false;
            vertices[i] = new double[]{px, py}; corners.add(px + ":" + py);
        }
        double area = 0;
        for (int i = 0; i < 4; i++) area += vertices[i][0] * vertices[(i + 1) % 4][1] - vertices[(i + 1) % 4][0] * vertices[i][1];
        return corners.size() == 4 && Math.abs(area) == 2;
    }
}
