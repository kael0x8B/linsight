package com.linsight.module.aivideo.service.algorithm;

import com.linsight.framework.common.exception.ServiceException;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.module.aivideo.dal.dataobject.algorithm.AlgorithmDO;
import com.linsight.module.aivideo.dal.dataobject.algorithm.PipelineVersionDO;
import com.linsight.module.aivideo.dal.mysql.algorithm.PipelineVersionMapper;
import com.linsight.module.aivideo.dal.mysql.algorithm.AlgorithmMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class AlgorithmServiceImplTest {

    @Mock private PipelineVersionMapper pipelineVersionMapper;
    @Mock private AlgorithmMapper algorithmMapper;
    @InjectMocks private AlgorithmServiceImpl service;

    @Test
    void modelRelationsIncludePublishedNodeOverridesOnceAndExcludeDrafts() {
        AlgorithmDO algorithm = new AlgorithmDO();
        algorithm.setId(1L);
        algorithm.setDefaultModelId(7L);
        algorithm.setCurrentPipelineVersionId(10L);
        PipelineVersionDO pipeline = new PipelineVersionDO();
        pipeline.setId(10L);
        pipeline.setValidationStatus("PUBLISHED");
        pipeline.setDag(JsonUtils.toJsonString(Map.of("acceptance", Map.of("status", "PENDING"),
                "nodes", List.of(
                        Map.of("modelId", 8L, "modelIds", List.of(8L, 18L)),
                        Map.of("modelId", 9L),
                        Map.of("modelId", 8L)))));
        when(algorithmMapper.selectEnabledList()).thenReturn(List.of(algorithm));
        when(pipelineVersionMapper.selectBatchIds(List.of(10L))).thenReturn(List.of(pipeline));

        var relations = service.getModelCapabilities();
        assertEquals(java.util.Set.of(7L, 8L, 9L, 18L), relations.keySet());
        assertEquals(1, relations.get(8L).size());
        assertEquals(1, relations.get(18L).size());
        assertEquals("PENDING", relations.get(8L).get(0).getAcceptanceStatus());

        pipeline.setValidationStatus("DRAFT");
        assertEquals(java.util.Set.of(7L), service.getModelCapabilities().keySet());
    }

    @Test
    void fieldValidationIsExplicitAndNeverChangesAcceptanceOrAllowsUnsupportedRuntime() {
        for (String status : List.of("PENDING", "BLOCKED_EXTERNAL_ASSETS")) {
            PipelineVersionDO pipeline = new PipelineVersionDO();
            pipeline.setDag(JsonUtils.toJsonString(Map.of("acceptance", Map.of("status", status))));
            String original = pipeline.getDag();
            assertThrows(ServiceException.class, () -> service.validatePipelineRunnable(pipeline));
            service.validatePipelineRunnable(pipeline, true);
            assertEquals(original, pipeline.getDag());
            assertThrows(ServiceException.class, () -> service.validatePipelineRunnable(pipeline, false));
        }
        PipelineVersionDO unsupported = new PipelineVersionDO();
        unsupported.setDag(JsonUtils.toJsonString(Map.of("acceptance", Map.of("status", "BLOCKED_RUNTIME_ADAPTER"))));
        assertThrows(ServiceException.class, () -> service.validatePipelineRunnable(unsupported, true));
    }

    @Test
    void acceptanceStatusesLoadPublishedPipelinesInOneBatch() {
        AlgorithmDO accepted = new AlgorithmDO();
        accepted.setId(1L);
        accepted.setCurrentPipelineVersionId(10L);
        AlgorithmDO blocked = new AlgorithmDO();
        blocked.setId(2L);
        blocked.setCurrentPipelineVersionId(20L);
        AlgorithmDO unpublished = new AlgorithmDO();
        unpublished.setId(3L);

        PipelineVersionDO acceptedPipeline = new PipelineVersionDO();
        acceptedPipeline.setId(10L);
        acceptedPipeline.setValidationStatus("PUBLISHED");
        acceptedPipeline.setDag(JsonUtils.toJsonString(Map.of(
                "schemaVersion", "1.0", "acceptance", Map.of("status", "PASS"))));
        PipelineVersionDO blockedPipeline = new PipelineVersionDO();
        blockedPipeline.setId(20L);
        blockedPipeline.setValidationStatus("PUBLISHED");
        blockedPipeline.setDag(JsonUtils.toJsonString(Map.of(
                "schemaVersion", "1.0", "acceptance", Map.of("status", "BLOCKED_EXTERNAL_ASSETS"))));
        when(pipelineVersionMapper.selectBatchIds(List.of(10L, 20L)))
                .thenReturn(List.of(acceptedPipeline, blockedPipeline));

        assertEquals(Map.of(
                        1L, "PASS",
                        2L, "BLOCKED_EXTERNAL_ASSETS",
                        3L, "UNPUBLISHED"),
                service.getPipelineAcceptanceStatuses(List.of(accepted, blocked, unpublished)));
    }

    @Test
    void validateDagAcceptsControlledAcyclicPipeline() {
        Map<String, Object> dag = Map.of(
                "schemaVersion", "1.0",
                "nodes", List.of(
                        Map.of("id", "detector", "type", "DETECTOR", "capabilityKey", "detector.person"),
                        Map.of("id", "tracker", "type", "TRACKER", "capabilityKey", "tracker.iou")
                ),
                "edges", List.of(Map.of("from", "detector", "to", "tracker"))
        );

        assertTrue(AlgorithmServiceImpl.validateDag(dag).isEmpty());
    }

    @Test
    void validateDagAcceptsMultipleHardwareTargetModelAssets() {
        Map<String, Object> dag = Map.of(
                "schemaVersion", "1.0",
                "nodes", List.of(
                        Map.of("id", "plate-detector", "type", "DETECTOR",
                                "capabilityKey", "detector.license-plate"),
                        Map.of("id", "plate-ocr", "type", "OCR",
                                "capabilityKey", "ocr.license-plate",
                                "modelId", 71036L,
                                "modelIds", List.of(71036L, 71039L)),
                        Map.of("id", "tracker", "type", "TRACKER",
                                "capabilityKey", "tracker.iou")),
                "edges", List.of(
                        Map.of("from", "plate-detector", "to", "plate-ocr"),
                        Map.of("from", "plate-ocr", "to", "tracker")));

        assertTrue(AlgorithmServiceImpl.validateDag(dag).isEmpty());
    }

    @Test
    void validateDagRejectsInvalidHardwareTargetModelAssets() {
        Map<String, Object> missingPrimary = Map.of(
                "schemaVersion", "1.0",
                "nodes", List.of(Map.of(
                        "id", "plate-ocr",
                        "type", "OCR",
                        "capabilityKey", "ocr.license-plate",
                        "modelId", 71036L,
                        "modelIds", List.of(71039L))),
                "edges", List.of());
        Map<String, Object> invalidId = Map.of(
                "schemaVersion", "1.0",
                "nodes", List.of(Map.of(
                        "id", "plate-ocr",
                        "type", "OCR",
                        "capabilityKey", "ocr.license-plate",
                        "modelIds", List.of(0))),
                "edges", List.of());

        assertTrue(AlgorithmServiceImpl.validateDag(missingPrimary).contains(
                "节点 modelId 必须包含在 modelIds 中"));
        assertTrue(AlgorithmServiceImpl.validateDag(invalidId).contains(
                "节点 modelIds 必须包含 1 至 32 个有效模型编号"));
    }

    @Test
    void validateDagAcceptsTenantDefinedCapabilityWithoutPerCapabilityWhitelist() {
        Map<String, Object> dag = Map.of(
                "schemaVersion", "1.0",
                "nodes", List.of(Map.of(
                        "id", "custom-detector",
                        "type", "DETECTOR",
                        "capabilityKey", "mine.belt-tear")),
                "edges", List.of(),
                "acceptance", Map.of("status", "PENDING")
        );

        assertTrue(AlgorithmServiceImpl.validateDag(dag).isEmpty());
    }

    @Test
    void validateDagRejectsVideoAcceptancePassWhenMetricsMissThreshold() {
        Map<String, Object> acceptance = new java.util.LinkedHashMap<>();
        acceptance.put("source", "VIDEO_ACCEPTANCE");
        acceptance.put("status", "PASS");
        acceptance.put("taskId", 1);
        acceptance.put("datasetVersion", "plant-a-v1");
        acceptance.put("datasetSha256", "a".repeat(64));
        acceptance.put("evidenceRef", "evidence/report-1.json");
        acceptance.put("cooldownDedupPass", true);
        acceptance.put("metrics", Map.of(
                "eventPrecision", 0.8,
                "eventRecall", 0.95,
                "falsePositivesPerStreamHour", 0.2,
                "missedEvents", 0,
                "endToEndP95Ms", 800,
                "averageFps", 5));
        acceptance.put("thresholds", Map.of(
                "minEventPrecision", 0.9,
                "minEventRecall", 0.9,
                "maxFalsePositivesPerStreamHour", 1,
                "maxMissedEvents", 0,
                "maxEndToEndP95Ms", 1000,
                "minAverageFps", 3));
        Map<String, Object> dag = Map.of(
                "schemaVersion", "1.0",
                "nodes", List.of(Map.of(
                        "id", "custom-detector",
                        "type", "DETECTOR",
                        "capabilityKey", "mine.belt-tear")),
                "edges", List.of(),
                "acceptance", acceptance);

        assertTrue(AlgorithmServiceImpl.validateDag(dag).stream()
                .anyMatch(value -> value.contains("指标未达到阈值")));
    }

    @Test
    void validateDagAcceptsAreaIntrusionVerticalPipeline() {
        Map<String, Object> dag = Map.of(
                "schemaVersion", "1.0",
                "nodes", List.of(
                        Map.of("id", "detector", "type", "DETECTOR", "capabilityKey", "detector.person"),
                        Map.of("id", "tracker", "type", "TRACKER", "capabilityKey", "tracker.iou"),
                        Map.of("id", "rule", "type", "RULE", "capabilityKey", "rule.area-intrusion")
                ),
                "edges", List.of(Map.of("from", "detector", "to", "tracker"),
                        Map.of("from", "tracker", "to", "rule"))
        );

        assertTrue(AlgorithmServiceImpl.validateDag(dag).isEmpty());
    }

    @Test
    void validateDagAcceptsGenericCocoCountPipeline() {
        Map<String, Object> dag = Map.of(
                "schemaVersion", "1.0",
                "nodes", List.of(
                        Map.of("id", "detector", "type", "DETECTOR", "capabilityKey", "detector.coco"),
                        Map.of("id", "tracker", "type", "TRACKER", "capabilityKey", "tracker.iou"),
                        Map.of("id", "rule", "type", "RULE", "capabilityKey", "rule.count")
                ),
                "edges", List.of(Map.of("from", "detector", "to", "tracker"),
                        Map.of("from", "tracker", "to", "rule")),
                "acceptance", Map.of("status", "PASS")
        );

        assertTrue(AlgorithmServiceImpl.validateDag(dag).isEmpty());
    }

    @Test
    void validateDagAcceptsBlockedFutureControlledNodeTypes() {
        for (Map.Entry<String, String> value : Map.of(
                "POSE", "pose.human",
                "SEGMENTER", "segmentation.general",
                "RECOGNIZER", "recognition.face",
                "QUALITY", "quality.video").entrySet()) {
            Map<String, Object> dag = Map.of(
                    "schemaVersion", "1.0",
                    "nodes", List.of(Map.of(
                            "id", "capability", "type", value.getKey(), "capabilityKey", value.getValue())),
                    "edges", List.of(),
                    "acceptance", Map.of("status", "BLOCKED_RUNTIME_ADAPTER")
            );
            assertTrue(AlgorithmServiceImpl.validateDag(dag).isEmpty());
        }
    }

    @Test
    void validateDagRejectsCyclesAndArbitraryNodes() {
        Map<String, Object> cyclic = Map.of(
                "schemaVersion", "1.0",
                "nodes", List.of(
                        Map.of("id", "a", "type", "DETECTOR", "capabilityKey", "detector.person"),
                        Map.of("id", "b", "type", "RULE", "capabilityKey", "rule.area-intrusion")
                ),
                "edges", List.of(Map.of("from", "a", "to", "b"), Map.of("from", "b", "to", "a"))
        );
        assertTrue(AlgorithmServiceImpl.validateDag(cyclic).contains("Pipeline DAG 存在循环依赖"));

        Map<String, Object> arbitrary = Map.of(
                "schemaVersion", "1.0",
                "nodes", List.of(Map.of("id", "script", "type", "PYTHON", "capabilityKey", "exec")),
                "edges", List.of()
        );
        assertEquals(List.of("节点必须包含唯一 id、受控 type 和 capabilityKey"),
                AlgorithmServiceImpl.validateDag(arbitrary));
    }

    @Test
    void validateDagRejectsIncompleteStoryElevenChain() {
        Map<String, Object> incomplete = Map.of(
                "schemaVersion", "1.0",
                "nodes", List.of(
                        Map.of("id", "person", "type", "DETECTOR", "capabilityKey", "detector.person"),
                        Map.of("id", "helmet", "type", "CLASSIFIER", "capabilityKey", "ppe.helmet"),
                        Map.of("id", "tracker", "type", "TRACKER", "capabilityKey", "tracker.iou")
                ),
                "edges", List.of(Map.of("from", "person", "to", "helmet"))
        );

        assertEquals(List.of("ppe.helmet 缺少受控链路：ppe.helmet->tracker.iou"),
                AlgorithmServiceImpl.validateDag(incomplete));
    }

    @Test
    void validateDagAcceptsBlockedButStructurallyValidPipeline() {
        Map<String, Object> dag = Map.of(
                "schemaVersion", "1.0",
                "nodes", List.of(Map.of(
                        "id", "flame", "type", "DETECTOR", "capabilityKey", "detector.flame")),
                "edges", List.of(),
                "acceptance", Map.of("status", "BLOCKED_EXTERNAL_ASSETS")
        );

        assertTrue(AlgorithmServiceImpl.validateDag(dag).isEmpty());
        assertEquals("BLOCKED_EXTERNAL_ASSETS", AlgorithmServiceImpl.acceptanceStatus(dag));
    }

    @Test
    void acceptanceDefaultsToPassButRejectsMalformedStatus() {
        assertEquals("PASS", AlgorithmServiceImpl.acceptanceStatus(Map.of()));
        assertEquals(List.of("acceptance.status 必须为 PASS、PENDING 或 BLOCKED_* 状态"),
                AlgorithmServiceImpl.validateDag(Map.of(
                        "schemaVersion", "1.0",
                        "nodes", List.of(Map.of(
                                "id", "flame", "type", "DETECTOR", "capabilityKey", "detector.flame")),
                        "edges", List.of(),
                        "acceptance", Map.of("status", "READY")
                )));
    }

    @Test
    void validatePipelineRunnableRejectsPendingAcceptance() {
        PipelineVersionDO pipeline = new PipelineVersionDO();
        pipeline.setDag(JsonUtils.toJsonString(Map.of(
                "schemaVersion", "1.0",
                "acceptance", Map.of("status", "PENDING")
        )));

        ServiceException error = assertThrows(ServiceException.class,
                () -> new AlgorithmServiceImpl().validatePipelineRunnable(pipeline));

        assertEquals(1_020_002_013, error.getCode());
        assertTrue(error.getMessage().contains("PENDING"));
    }
}
