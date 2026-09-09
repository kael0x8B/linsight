package com.linsight.module.aivideo.service.rule;

import java.time.LocalTime;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

final class RuleAstValidator {
    private static final Set<String> SEVERITIES = Set.of("INFO", "MINOR", "MAJOR", "CRITICAL");
    private static final Set<String> POINT_MODES = Set.of("CENTROID", "FOOT", "OVERLAP");

    private RuleAstValidator() {}

    static List<String> validate(Map<String, Object> ast, String expectedEventType) {
        List<String> errors = new ArrayList<>();
        if (ast == null || !"1.0".equals(ast.get("schemaVersion"))) {
            return List.of("schemaVersion 必须为 1.0");
        }
        if (!expectedEventType.equals(ast.get("eventType"))) errors.add("eventType 必须与规则定义一致");
        if (!SEVERITIES.contains(ast.get("severity"))) errors.add("severity 不受支持");
        Set<String> regionIds = validateRegions(ast.get("regions"), errors);
        validateSchedule(ast.get("schedule"), errors);
        if (!(ast.get("condition") instanceof Map<?, ?> condition)) {
            errors.add("condition 必须是规则节点");
        } else {
            validateCondition(condition, regionIds, errors, "condition");
        }
        validateSeconds(ast.get("cooldownSeconds"), "cooldownSeconds", 0, 86400, errors);
        validateSeconds(ast.get("recoverySeconds"), "recoverySeconds", 0, 86400, errors);
        if (!(ast.get("dedup") instanceof Map<?, ?> dedup)
                || !(dedup.get("scope") instanceof String scope)
                || !Set.of("TRACK", "CAMERA_TASK_TYPE").contains(scope)) {
            errors.add("dedup.scope 必须为 TRACK 或 CAMERA_TASK_TYPE");
        } else {
            validateSeconds(dedup.get("windowSeconds"), "dedup.windowSeconds", 1, 86400, errors);
        }
        return errors;
    }

    static String summarize(Map<String, Object> ast) {
        RuleThresholds thresholds = RuleThresholds.from(ast);
        String regionName = "指定区域";
        if (ast.get("regions") instanceof List<?> regions && !regions.isEmpty()
                && regions.get(0) instanceof Map<?, ?> region && region.get("name") instanceof String name) {
            regionName = name;
        }
        return "目标进入" + regionName + "，" + thresholds.m() + " 帧中至少 " + thresholds.n()
                + " 帧且持续 " + formatSeconds(thresholds.durationSeconds()) + " 秒后告警；同一目标冷却 "
                + formatSeconds(number(ast.get("cooldownSeconds"), 0)) + " 秒。";
    }

    static RuleRegion firstRegion(Map<String, Object> ast) {
        if (!(ast.get("regions") instanceof List<?> regions) || regions.isEmpty()
                || !(regions.get(0) instanceof Map<?, ?> region)) {
            throw new IllegalArgumentException("rule region is missing");
        }
        List<Point> points = new ArrayList<>();
        for (Object value : (List<?>) region.get("points")) {
            Map<?, ?> point = (Map<?, ?>) value;
            points.add(new Point(number(point.get("x"), 0), number(point.get("y"), 0)));
        }
        return new RuleRegion(String.valueOf(region.get("id")), String.valueOf(region.get("pointMode")),
                number(region.get("overlapThreshold"), 0), points);
    }

    static boolean contains(RuleRegion region, double x, double y) {
        boolean inside = false;
        List<Point> points = region.points();
        for (int i = 0, j = points.size() - 1; i < points.size(); j = i++) {
            Point left = points.get(i);
            Point right = points.get(j);
            if ((left.y() > y) != (right.y() > y)
                    && x < (right.x() - left.x()) * (y - left.y()) / (right.y() - left.y()) + left.x()) {
                inside = !inside;
            }
        }
        return inside;
    }

    private static Set<String> validateRegions(Object value, List<String> errors) {
        Set<String> ids = new HashSet<>();
        if (!(value instanceof List<?> regions) || regions.isEmpty()) {
            errors.add("regions 至少包含一个多边形");
            return ids;
        }
        for (int index = 0; index < regions.size(); index++) {
            Object item = regions.get(index);
            String path = "regions[" + index + "]";
            if (!(item instanceof Map<?, ?> region) || !(region.get("id") instanceof String id) || id.isBlank()) {
                errors.add(path + ".id 不能为空");
                continue;
            }
            if (!ids.add(id)) errors.add(path + ".id 重复");
            if (!"POLYGON".equals(region.get("type"))) errors.add(path + ".type 必须为 POLYGON");
            if (!POINT_MODES.contains(region.get("pointMode"))) errors.add(path + ".pointMode 不受支持");
            validateDimensions(region, path, errors);
            validatePolygon(region.get("points"), path, errors);
        }
        return ids;
    }

    private static void validateDimensions(Map<?, ?> region, String path, List<String> errors) {
        if (!(region.get("sourceWidth") instanceof Number width) || width.intValue() <= 0
                || !(region.get("sourceHeight") instanceof Number height) || height.intValue() <= 0) {
            errors.add(path + " 必须保存正数 sourceWidth/sourceHeight");
        }
        double overlap = number(region.get("overlapThreshold"), 0);
        if (overlap < 0 || overlap > 1) errors.add(path + ".overlapThreshold 必须在 [0,1]");
    }

    private static void validatePolygon(Object value, String path, List<String> errors) {
        if (!(value instanceof List<?> values) || values.size() < 3) {
            errors.add(path + ".points 至少包含 3 个点");
            return;
        }
        List<Point> points = new ArrayList<>();
        for (Object item : values) {
            if (!(item instanceof Map<?, ?> point) || !(point.get("x") instanceof Number x)
                    || !(point.get("y") instanceof Number y) || x.doubleValue() < 0 || x.doubleValue() > 1
                    || y.doubleValue() < 0 || y.doubleValue() > 1) {
                errors.add(path + ".points 坐标必须归一化到 [0,1]");
                return;
            }
            points.add(new Point(x.doubleValue(), y.doubleValue()));
        }
        if (polygonArea(points) < 0.0001) errors.add(path + " 多边形面积过小");
        if (selfIntersects(points)) errors.add(path + " 多边形存在自交");
    }

    private static void validateSchedule(Object value, List<String> errors) {
        if (!(value instanceof Map<?, ?> schedule)) {
            errors.add("schedule 必须存在");
            return;
        }
        try {
            ZoneId.of(String.valueOf(schedule.get("timezone")));
        } catch (RuntimeException ignored) {
            errors.add("schedule.timezone 无效");
        }
        if (!(schedule.get("weekly") instanceof List<?> weekly) || weekly.isEmpty()) {
            errors.add("schedule.weekly 至少包含一个时段");
            return;
        }
        for (Object item : weekly) {
            if (!(item instanceof Map<?, ?> slot) || !(slot.get("days") instanceof List<?> days)
                    || days.isEmpty() || days.stream().anyMatch(day -> !(day instanceof Number number)
                    || number.intValue() < 1 || number.intValue() > 7)) {
                errors.add("schedule.weekly.days 必须为 1..7");
                continue;
            }
            try {
                LocalTime.parse(String.valueOf(slot.get("start")));
                LocalTime.parse(String.valueOf(slot.get("end")));
            } catch (RuntimeException ignored) {
                errors.add("schedule.weekly 时间必须为 HH:mm");
            }
        }
    }

    private static void validateCondition(Map<?, ?> condition, Set<String> regionIds,
                                          List<String> errors, String path) {
        Object typeValue = condition.get("type");
        if (!(typeValue instanceof String type)) {
            errors.add(path + ".type 不能为空");
            return;
        }
        switch (type) {
            case "AND", "OR" -> {
                if (!(condition.get("children") instanceof List<?> children) || children.isEmpty()) {
                    errors.add(path + ".children 不能为空");
                } else {
                    for (int i = 0; i < children.size(); i++) {
                        if (children.get(i) instanceof Map<?, ?> child) {
                            validateCondition(child, regionIds, errors, path + ".children[" + i + "]");
                        } else errors.add(path + ".children[" + i + "] 必须是规则节点");
                    }
                }
            }
            case "NOT" -> {
                if (condition.get("child") instanceof Map<?, ?> child) {
                    validateCondition(child, regionIds, errors, path + ".child");
                } else errors.add(path + ".child 必须是规则节点");
            }
            case "ROI_ENTER" -> {
                if (!(condition.get("regionId") instanceof String regionId) || !regionIds.contains(regionId)) {
                    errors.add(path + ".regionId 引用了不存在的区域");
                }
                if (!(condition.get("objectClasses") instanceof List<?> classes) || classes.isEmpty()) {
                    errors.add(path + ".objectClasses 不能为空");
                }
            }
            case "N_OF_M" -> {
                int n = integer(condition.get("n"), -1);
                int m = integer(condition.get("m"), -1);
                if (n < 1 || m < n || m > 300) errors.add(path + " 必须满足 1 <= n <= m <= 300");
            }
            case "DURATION" -> validateSeconds(condition.get("seconds"), path + ".seconds", 0, 86400, errors);
            case "COUNT" -> {
                if (integer(condition.get("min"), 0) < 1) errors.add(path + ".min 必须大于 0");
            }
            case "COUNT_BELOW" -> {
                if (integer(condition.get("min"), 0) < 1) errors.add(path + ".min 必须大于 0");
                if (!(condition.get("regionId") instanceof String regionId)
                        || !regionIds.contains(regionId)) {
                    errors.add(path + ".regionId 引用了不存在的区域");
                }
                if (!(condition.get("objectClasses") instanceof List<?> classes)
                        || classes.isEmpty()) {
                    errors.add(path + ".objectClasses 不能为空");
                }
            }
            case "STATIONARY" -> validateRatio(condition.get("maxMovement"), path + ".maxMovement", errors);
            case "LOITERING" -> {
                validateRatio(condition.get("minPathLength"), path + ".minPathLength", errors);
                validateSeconds(condition.get("seconds"), path + ".seconds", 1, 86400, errors);
            }
            default -> errors.add(path + ".type 不受支持：" + type);
        }
    }

    private static void validateRatio(Object value, String field, List<String> errors) {
        if (!(value instanceof Number number) || number.doubleValue() <= 0 || number.doubleValue() > 1) {
            errors.add(field + " 必须在 (0,1]");
        }
    }

    private static void validateSeconds(Object value, String field, double min, double max,
                                        List<String> errors) {
        if (!(value instanceof Number number) || number.doubleValue() < min || number.doubleValue() > max) {
            errors.add(field + " 必须在 " + min + ".." + max);
        }
    }

    private static double polygonArea(List<Point> points) {
        double area = 0;
        for (int i = 0; i < points.size(); i++) {
            Point left = points.get(i);
            Point right = points.get((i + 1) % points.size());
            area += left.x() * right.y() - right.x() * left.y();
        }
        return Math.abs(area) / 2;
    }

    private static boolean selfIntersects(List<Point> points) {
        int size = points.size();
        for (int i = 0; i < size; i++) {
            Point a1 = points.get(i);
            Point a2 = points.get((i + 1) % size);
            for (int j = i + 1; j < size; j++) {
                if (j == i || j == (i + 1) % size || (j + 1) % size == i) continue;
                if (segmentsIntersect(a1, a2, points.get(j), points.get((j + 1) % size))) return true;
            }
        }
        return false;
    }

    private static boolean segmentsIntersect(Point a, Point b, Point c, Point d) {
        double abC = cross(a, b, c);
        double abD = cross(a, b, d);
        double cdA = cross(c, d, a);
        double cdB = cross(c, d, b);
        return abC * abD < 0 && cdA * cdB < 0;
    }

    private static double cross(Point a, Point b, Point c) {
        return (b.x() - a.x()) * (c.y() - a.y()) - (b.y() - a.y()) * (c.x() - a.x());
    }

    private static int integer(Object value, int fallback) {
        return value instanceof Number number ? number.intValue() : fallback;
    }

    private static double number(Object value, double fallback) {
        return value instanceof Number number ? number.doubleValue() : fallback;
    }

    private static String formatSeconds(double seconds) {
        return seconds == Math.rint(seconds) ? String.valueOf((int) seconds) : String.valueOf(seconds);
    }

    record Point(double x, double y) {}
    record RuleRegion(String id, String pointMode, double overlapThreshold, List<Point> points) {}

    record RuleThresholds(int n, int m, double durationSeconds) {
        static RuleThresholds from(Map<String, Object> ast) {
            MutableThresholds values = new MutableThresholds();
            if (ast.get("condition") instanceof Map<?, ?> condition) collect(condition, values);
            return new RuleThresholds(values.n, values.m, values.durationSeconds);
        }

        private static void collect(Map<?, ?> node, MutableThresholds values) {
            String type = String.valueOf(node.get("type"));
            if ("N_OF_M".equals(type)) {
                values.n = integer(node.get("n"), 1);
                values.m = integer(node.get("m"), 1);
            } else if ("DURATION".equals(type)) {
                values.durationSeconds = number(node.get("seconds"), 0);
            }
            if (node.get("children") instanceof List<?> children) {
                children.forEach(child -> { if (child instanceof Map<?, ?> map) collect(map, values); });
            }
            if (node.get("child") instanceof Map<?, ?> child) collect(child, values);
        }
    }

    private static final class MutableThresholds {
        private int n = 1;
        private int m = 1;
        private double durationSeconds;
    }
}
