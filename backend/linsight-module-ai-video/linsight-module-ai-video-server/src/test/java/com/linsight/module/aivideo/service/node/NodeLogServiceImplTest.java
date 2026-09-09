package com.linsight.module.aivideo.service.node;

import com.linsight.module.aivideo.controller.node.node.vo.NodeLogEntryReqVO;
import com.linsight.module.aivideo.dal.dataobject.node.EdgeNodeDO;
import com.linsight.module.aivideo.dal.dataobject.node.NodeDiagnosticBundleDO;
import com.linsight.module.aivideo.dal.dataobject.node.NodeLogDO;
import com.linsight.module.aivideo.dal.mysql.node.EdgeNodeMapper;
import com.linsight.module.aivideo.dal.mysql.node.NodeDiagnosticBundleMapper;
import com.linsight.module.aivideo.dal.mysql.node.NodeLogMapper;
import com.linsight.module.infra.api.file.FileApi;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.LocalDateTime;
import java.time.ZoneId;
import java.nio.charset.StandardCharsets;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class NodeLogServiceImplTest {
    @Mock private NodeLogMapper nodeLogMapper;
    @Mock private NodeDiagnosticBundleMapper diagnosticMapper;
    @Mock private EdgeNodeMapper edgeNodeMapper;
    @Mock private NodeService nodeService;
    @Mock private FileApi fileApi;
    @org.mockito.Spy private NodeLogProperties logProperties = new NodeLogProperties();
    @InjectMocks private NodeLogServiceImpl service;

    @Test
    void routineInfoIsDroppedBeforeDatabaseLookupButHttpFailuresArePreserved() {
        NodeLogEntryReqVO routine = logEntry("noise");
        routine.setLevel("INFO");
        routine.setMessage("HTTP Request: POST http://localhost/logs \"HTTP/1.1 200 OK\"");
        NodeLogEntryReqVO heartbeat = logEntry("heartbeat");
        heartbeat.setLevel("INFO");
        heartbeat.setMessage("Heartbeat accepted nodeId=9 sequence=1");
        service.ingest(9L, List.of(routine, heartbeat));
        org.mockito.Mockito.verifyNoInteractions(nodeLogMapper);
        routine.setMessage("HTTP Request: POST http://localhost/logs \"HTTP/1.1 500 Error\"");
        service.ingest(9L, List.of(routine));
        verify(nodeLogMapper).insert(any(NodeLogDO.class));
        org.junit.jupiter.api.Assertions.assertFalse(NodeLogPolicy.isRoutineNoise("WARN", "EDGE_AGENT", heartbeat.getMessage()));
    }

    @Test
    void retentionDrainsMoreThanOneBatchAndKeepsBoundedPerSeverityBudget() {
        logProperties.setCleanupMaxBatches(2);
        when(nodeLogMapper.deleteExpiredGlobal(org.mockito.ArgumentMatchers.anyString(), any(), eq(5000)))
                .thenAnswer(call -> "INFO".equals(call.getArgument(0)) ? 5000 : 0);
        assertEquals(10000, service.cleanupExpiredLogs());
        verify(nodeLogMapper, org.mockito.Mockito.times(2)).deleteExpiredGlobal(eq("INFO"), any(), eq(5000));
        verify(nodeLogMapper).deleteExpiredGlobal(eq("ERROR"), any(), eq(5000));
    }

    @Test
    void ingestMustBeIdempotentAndRedactBeforePersistence() {
        NodeLogEntryReqVO entry = logEntry("entry-1");
        when(nodeLogMapper.selectByNodeAndEntry(9L, "entry-1")).thenReturn(null);

        service.ingest(9L, List.of(entry));

        ArgumentCaptor<NodeLogDO> inserted = ArgumentCaptor.forClass(NodeLogDO.class);
        verify(nodeLogMapper).insert(inserted.capture());
        assertFalse(inserted.getValue().getMessage().contains("camera-pass"));
        assertFalse(inserted.getValue().getContextJson().contains("runtime-secret"));
        assertEquals("edge-agent", inserted.getValue().getCreator());

        when(nodeLogMapper.selectByNodeAndEntry(9L, "entry-1")).thenReturn(inserted.getValue());
        service.ingest(9L, List.of(entry));
        verify(nodeLogMapper).insert(any(NodeLogDO.class));
    }

    @Test
    void diagnosticBuildMustCreatePrivateZipAndPersistOnlyInternalReference() {
        NodeDiagnosticBundleDO bundle = new NodeDiagnosticBundleDO();
        bundle.setId(5L);
        bundle.setNodeId(9L);
        bundle.setStatus("QUEUED");
        bundle.setRangeStart(LocalDateTime.now().minusMinutes(10));
        bundle.setRangeEnd(LocalDateTime.now());
        EdgeNodeDO node = new EdgeNodeDO();
        node.setId(9L);
        node.setCode("EDGE-9");
        node.setAgentVersion("1.0.0");
        node.setCredentialDigest("must-not-be-exported");
        NodeLogDO log = new NodeLogDO();
        log.setMessage("safe log line");
        when(diagnosticMapper.selectById(5L)).thenReturn(bundle);
        when(edgeNodeMapper.selectById(9L)).thenReturn(node);
        when(nodeLogMapper.selectForDiagnostic(eq(9L), eq(null), any(), any()))
                .thenReturn(List.of(log));
        when(fileApi.createFile(any(byte[].class), eq("linsight-diagnostic-node-9-5.zip"),
                eq("ai-video/diagnostics/9"), eq("application/zip"))).thenReturn("private-ref");

        service.buildDiagnostic(5L);

        assertEquals("READY", bundle.getStatus());
        assertEquals("private-ref", bundle.getFileRef());
        assertEquals(1, bundle.getLogCount());
        ArgumentCaptor<byte[]> content = ArgumentCaptor.forClass(byte[].class);
        verify(fileApi).createFile(content.capture(), any(), any(), any());
        assertEquals(0x50, Byte.toUnsignedInt(content.getValue()[0]));
        assertEquals(0x4b, Byte.toUnsignedInt(content.getValue()[1]));
        assertFalse(new String(content.getValue(), StandardCharsets.ISO_8859_1)
                .contains("must-not-be-exported"));
    }

    private static NodeLogEntryReqVO logEntry(String entryId) {
        NodeLogEntryReqVO entry = new NodeLogEntryReqVO();
        entry.setEntryId(entryId);
        entry.setComponent("EDGE_AGENT");
        entry.setLevel("ERROR");
        entry.setMessage("failed rtsp://admin:camera-pass@10.0.0.8/live");
        entry.setContextJson("{\"runtime_api_key\":\"runtime-secret\"}");
        entry.setTimestampMillis(LocalDateTime.now().atZone(ZoneId.systemDefault())
                .toInstant().toEpochMilli());
        return entry;
    }
}
