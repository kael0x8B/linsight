package com.linsight.module.aivideo.service.rule;

import com.linsight.module.aivideo.controller.admin.rule.vo.RuleDryRunReqVO;
import com.linsight.module.aivideo.controller.admin.rule.vo.RuleDryRunRespVO;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.Map;
import java.util.Set;

final class RuleDryRunEngine {
    private RuleDryRunEngine() {}

    static RuleDryRunRespVO run(Map<String, Object> ast, List<RuleDryRunReqVO.Frame> frames) {
        RuleAstValidator.RuleRegion region = RuleAstValidator.firstRegion(ast);
        RuleAstValidator.RuleThresholds thresholds = RuleAstValidator.RuleThresholds.from(ast);
        Set<String> classes = objectClasses(ast);
        Deque<Boolean> window = new ArrayDeque<>();
        Long stableSince = null;
        Long confirmedAt = null;
        List<RuleDryRunRespVO.FrameResult> results = new ArrayList<>();
        for (RuleDryRunReqVO.Frame frame : frames.stream()
                .sorted((left, right) -> Long.compare(left.getTimestampMillis(), right.getTimestampMillis())).toList()) {
            boolean roiMatched = frame.getObjects().stream().anyMatch(object ->
                    classes.contains(object.getClassName()) && matches(region, object.getBbox()));
            window.addLast(roiMatched);
            while (window.size() > thresholds.m()) window.removeFirst();
            int matchedFrames = (int) window.stream().filter(Boolean::booleanValue).count();
            boolean stable = window.size() >= thresholds.n() && matchedFrames >= thresholds.n();
            if (stable && stableSince == null) stableSince = frame.getTimestampMillis();
            if (!stable) stableSince = null;
            boolean confirmed = stableSince != null && frame.getTimestampMillis() - stableSince
                    >= Math.round(thresholds.durationSeconds() * 1000);
            String state = roiMatched ? "DETECTED" : "IDLE";
            if (stable) state = confirmed ? "CONFIRMED" : "PENDING";
            if (confirmed && confirmedAt == null) confirmedAt = frame.getTimestampMillis();
            results.add(new RuleDryRunRespVO.FrameResult(frame.getTimestampMillis(), roiMatched,
                    matchedFrames, state));
        }
        return new RuleDryRunRespVO(confirmedAt != null, confirmedAt, results);
    }

    private static boolean matches(RuleAstValidator.RuleRegion region, RuleDryRunReqVO.Bbox bbox) {
        double x = bbox.getX() + bbox.getWidth() / 2;
        double y = "FOOT".equals(region.pointMode()) ? bbox.getY() + bbox.getHeight()
                : bbox.getY() + bbox.getHeight() / 2;
        return RuleAstValidator.contains(region, x, y);
    }

    private static Set<String> objectClasses(Map<String, Object> ast) {
        Object condition = ast.get("condition");
        List<String> values = new ArrayList<>();
        collectClasses(condition, values);
        return values.isEmpty() ? Set.of("person") : Set.copyOf(values);
    }

    private static void collectClasses(Object value, List<String> result) {
        if (!(value instanceof Map<?, ?> node)) return;
        if (node.get("objectClasses") instanceof List<?> classes) {
            classes.stream().filter(String.class::isInstance).map(String.class::cast).forEach(result::add);
        }
        if (node.get("children") instanceof List<?> children) children.forEach(child -> collectClasses(child, result));
        collectClasses(node.get("child"), result);
    }
}
