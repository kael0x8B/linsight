package com.linsight.module.aivideo.service.rule;

import com.fasterxml.jackson.databind.JsonNode;

import java.util.ArrayList;
import java.util.List;

/** Display-only projection: never includes conditions, parameters or credentials. */
public record RuleRegionGeometryDTO(String id, String name, List<Point> points) {
    public record Point(double x, double y) {}

    public static List<RuleRegionGeometryDTO> fromRule(JsonNode rule) {
        var regions = rule.path("regions");
        if (!regions.isArray() || regions.size() > 64) return List.of();
        var result = new ArrayList<RuleRegionGeometryDTO>();
        for (var region : regions) {
            var raw = region.path("points");
            if (!raw.isArray() || raw.size() < 3 || raw.size() > 20) continue;
            var points = new ArrayList<Point>();
            for (var point : raw) {
                if (!coordinate(point.path("x")) || !coordinate(point.path("y"))) break;
                points.add(new Point(point.path("x").asDouble(), point.path("y").asDouble()));
            }
            if (points.size() == raw.size()) result.add(new RuleRegionGeometryDTO(
                    region.path("id").asText(""), region.path("name").asText(""), List.copyOf(points)));
        }
        return List.copyOf(result);
    }

    private static boolean coordinate(JsonNode value) {
        return value.isNumber() && Double.isFinite(value.asDouble())
                && value.asDouble() >= 0 && value.asDouble() <= 1;
    }
}
