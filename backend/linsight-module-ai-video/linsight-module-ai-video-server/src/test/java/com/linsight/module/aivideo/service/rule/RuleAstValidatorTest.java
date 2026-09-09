package com.linsight.module.aivideo.service.rule;

import com.linsight.module.aivideo.controller.admin.rule.vo.RuleDryRunReqVO;
import com.linsight.module.aivideo.controller.admin.rule.vo.RuleDryRunRespVO;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RuleAstValidatorTest {

    @Test
    void validatesAndSummarizesAreaIntrusionAst() {
        Map<String, Object> ast = ast();

        assertTrue(RuleAstValidator.validate(ast, "AREA_INTRUSION").isEmpty());
        assertEquals("目标进入主区域，5 帧中至少 3 帧且持续 2 秒后告警；同一目标冷却 30 秒。",
                RuleAstValidator.summarize(ast));
    }

    @Test
    void rejectsSelfIntersectingPolygon() {
        Map<String, Object> ast = ast();
        region(ast).put("points", List.of(
                point(0.1, 0.1), point(0.9, 0.9), point(0.1, 0.9), point(0.9, 0.1)));

        assertTrue(RuleAstValidator.validate(ast, "AREA_INTRUSION").stream()
                .anyMatch(value -> value.contains("自交")));
    }

    @Test
    void dryRunRequiresFrameStabilityAndDuration() {
        List<RuleDryRunReqVO.Frame> frames = List.of(
                frame(0, true), frame(100, true), frame(200, true), frame(1000, true), frame(2200, true));

        RuleDryRunRespVO result = RuleDryRunEngine.run(ast(), frames);

        assertTrue(result.isMatched());
        assertNotNull(result.getConfirmedAtMillis());
        assertEquals(2200L, result.getConfirmedAtMillis());
        assertFalse(result.getFrames().get(2).getState().equals("CONFIRMED"));
        assertEquals("CONFIRMED", result.getFrames().get(4).getState());
    }

    @Test
    void acceptsPersonAbsenceCountBelowCondition() {
        Map<String, Object> value = ast();
        value.put("eventType", "PERSON_ABSENCE");
        value.put("condition", Map.of("type", "AND", "children", List.of(
                Map.of("type", "COUNT_BELOW", "regionId", "main",
                        "objectClasses", List.of("person"), "min", 1),
                Map.of("type", "N_OF_M", "n", 3, "m", 5),
                Map.of("type", "DURATION", "seconds", 10))));

        assertTrue(RuleAstValidator.validate(value, "PERSON_ABSENCE").isEmpty());
    }

    @Test
    void acceptsStationaryAndLoiteringConditions() {
        Map<String, Object> value = ast();
        value.put("condition", Map.of("type", "AND", "children", List.of(
                Map.of("type", "ROI_ENTER", "regionId", "main", "objectClasses", List.of("person")),
                Map.of("type", "STATIONARY", "maxMovement", 0.02),
                Map.of("type", "LOITERING", "minPathLength", 0.1, "seconds", 30),
                Map.of("type", "N_OF_M", "n", 2, "m", 3))));

        assertTrue(RuleAstValidator.validate(value, "AREA_INTRUSION").isEmpty());
    }

    private static Map<String, Object> ast() {
        Map<String, Object> ast = new LinkedHashMap<>();
        ast.put("schemaVersion", "1.0");
        ast.put("eventType", "AREA_INTRUSION");
        ast.put("severity", "MAJOR");
        ast.put("regions", new ArrayList<>(List.of(new LinkedHashMap<>(Map.of(
                "id", "main",
                "name", "主区域",
                "type", "POLYGON",
                "sourceWidth", 1920,
                "sourceHeight", 1080,
                "pointMode", "FOOT",
                "overlapThreshold", 0,
                "points", List.of(point(0.1, 0.1), point(0.9, 0.1), point(0.9, 0.9), point(0.1, 0.9))
        )))));
        ast.put("schedule", Map.of("timezone", "Asia/Shanghai", "weekly", List.of(
                Map.of("days", List.of(1, 2, 3, 4, 5, 6, 7), "start", "00:00", "end", "23:59"))));
        ast.put("condition", Map.of("type", "AND", "children", List.of(
                Map.of("type", "ROI_ENTER", "regionId", "main", "objectClasses", List.of("person")),
                Map.of("type", "N_OF_M", "n", 3, "m", 5),
                Map.of("type", "DURATION", "seconds", 2))));
        ast.put("cooldownSeconds", 30);
        ast.put("recoverySeconds", 5);
        ast.put("dedup", Map.of("scope", "TRACK", "windowSeconds", 30));
        return ast;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> region(Map<String, Object> ast) {
        return (Map<String, Object>) ((List<?>) ast.get("regions")).get(0);
    }

    private static Map<String, Object> point(double x, double y) {
        return Map.of("x", x, "y", y);
    }

    private static RuleDryRunReqVO.Frame frame(long timestamp, boolean inside) {
        RuleDryRunReqVO.Bbox bbox = new RuleDryRunReqVO.Bbox();
        bbox.setX(inside ? 0.4 : 0.95);
        bbox.setY(0.3);
        bbox.setWidth(0.1);
        bbox.setHeight(0.2);
        RuleDryRunReqVO.DetectedObject object = new RuleDryRunReqVO.DetectedObject();
        object.setClassName("person");
        object.setTrackId("track-1");
        object.setBbox(bbox);
        RuleDryRunReqVO.Frame frame = new RuleDryRunReqVO.Frame();
        frame.setTimestampMillis(timestamp);
        frame.setObjects(List.of(object));
        return frame;
    }
}
