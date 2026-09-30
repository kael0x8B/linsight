package com.linsight.module.aivideo.service.task;

import com.baomidou.mybatisplus.core.conditions.Wrapper;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.module.aivideo.dal.dataobject.task.TaskDO;
import com.linsight.module.aivideo.dal.mysql.task.TaskMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class TaskRegionProjectionTest {
    private final TaskMapper mapper = mock(TaskMapper.class);
    private final TaskServiceImpl service = new TaskServiceImpl();
    private final TaskDO task = new TaskDO();
    private final Map<String, Object> configuration = new HashMap<>();
    private final Map<String, Object> metrics = new HashMap<>();
    private final List<Map<String, Double>> points = List.of(
            Map.of("x", .2, "y", .3), Map.of("x", .7, "y", .3),
            Map.of("x", .7, "y", .8), Map.of("x", .2, "y", .8));

    @BeforeEach
    @SuppressWarnings("unchecked")
    void setUp() {
        ReflectionTestUtils.setField(service, "taskMapper", mapper);
        task.setId(33L); task.setCameraId(2L); task.setConfigVersion(3);
        task.setRuleId(73018L); task.setRuleVersionId(73123L);
        when(mapper.selectList(any(Wrapper.class))).thenReturn(List.of(task));
        configuration.put("taskId", 33); configuration.put("cameraId", 2);
        configuration.put("sourceUrl", "private-camera-address");
        configuration.put("rule", Map.of("regions", List.of(Map.of(
                "id", "plate", "name", "车牌区域", "points", points,
                "privateExtra", "not-a-display-field")), "condition", Map.of("type", "AND")));
        metrics.put("gatewayConfiguration", configuration);
        metrics.put("gatewayRevision", 7); metrics.put("gatewayAppliedRevision", 7);
    }

    private TaskCameraCapabilityDTO projection() {
        task.setMetricsSnapshot(JsonUtils.toJsonString(metrics));
        return service.getCameraCapabilities(List.of(2L)).get(0);
    }

    @Test
    void exposesOnlyAppliedGeometryWithoutConfigurationOrCredentials() {
        var regions = projection().regions();
        assertThat(regions).hasSize(1);
        assertThat(regions.get(0).points().get(0).x()).isEqualTo(.2);
        assertThat(JsonUtils.toJsonString(regions)).contains("车牌区域")
                .doesNotContain("private-camera-address", "privateExtra", "condition");
    }

    @Test
    void pendingDeviceRevisionCannotAppearAsTheAppliedRegion() {
        metrics.put("gatewayAppliedRevision", 6);
        assertThat(projection().regions()).isEmpty();
    }

    @Test
    void anotherCameraOrTaskCannotContributeItsRegion() {
        configuration.put("cameraId", 99);
        assertThat(projection().regions()).isEmpty();
        configuration.put("cameraId", 2); configuration.put("taskId", 99);
        assertThat(projection().regions()).isEmpty();
    }

    @Test
    void missingRuntimeRegionDoesNotFallBackToThePublishedTemplate() {
        configuration.remove("rule");
        assertThat(projection().regions()).isEmpty();
        metrics.clear();
        assertThat(projection().regions()).isEmpty();
    }

    @Test
    void invalidCoordinatesAreOmitted() {
        configuration.put("rule", Map.of("regions", List.of(Map.of("points", List.of(
                Map.of("x", -1, "y", 0), Map.of("x", 1, "y", 0), Map.of("x", 1, "y", 1))))));
        assertThat(projection().regions()).isEmpty();
    }
}
