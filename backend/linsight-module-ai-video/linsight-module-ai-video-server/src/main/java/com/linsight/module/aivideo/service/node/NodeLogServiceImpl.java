package com.linsight.module.aivideo.service.node;

import com.linsight.framework.common.pojo.PageResult;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.framework.common.util.object.BeanUtils;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeDiagnosticCreateReqVO;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeDiagnosticRespVO;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeLogPageReqVO;
import com.linsight.module.aivideo.controller.admin.node.vo.NodeLogRespVO;
import com.linsight.module.aivideo.controller.node.node.vo.NodeLogEntryReqVO;
import com.linsight.module.aivideo.dal.dataobject.node.EdgeNodeDO;
import com.linsight.module.aivideo.dal.dataobject.node.NodeDiagnosticBundleDO;
import com.linsight.module.aivideo.dal.dataobject.node.NodeLogDO;
import com.linsight.module.aivideo.dal.mysql.node.EdgeNodeMapper;
import com.linsight.module.aivideo.dal.mysql.node.NodeDiagnosticBundleMapper;
import com.linsight.module.aivideo.dal.mysql.node.NodeLogMapper;
import com.linsight.module.aivideo.framework.security.SensitiveTextRedactor;
import com.linsight.module.infra.api.file.FileApi;
import jakarta.annotation.Resource;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

import static com.linsight.framework.common.exception.util.ServiceExceptionUtil.exception;
import static com.linsight.module.aivideo.enums.node.ErrorCodeConstants.NODE_DIAGNOSTIC_NOT_FOUND;
import static com.linsight.module.aivideo.enums.node.ErrorCodeConstants.NODE_DIAGNOSTIC_RANGE_INVALID;
import static com.linsight.module.aivideo.enums.node.ErrorCodeConstants.NODE_LOG_NOT_FOUND;

@Service
public class NodeLogServiceImpl implements NodeLogService {
    private static final int DOWNLOAD_TTL_SECONDS = 300;

    @Resource private NodeLogMapper nodeLogMapper;
    @Resource private NodeDiagnosticBundleMapper diagnosticMapper;
    @Resource private EdgeNodeMapper edgeNodeMapper;
    @Resource private NodeService nodeService;
    @Resource private FileApi fileApi;
    @Resource private NodeLogProperties logProperties;

    @Override
    public void ingest(Long nodeId, List<NodeLogEntryReqVO> entries) {
        nodeService.validateNodeExists(nodeId);
        LocalDateTime now = LocalDateTime.now();
        for (NodeLogEntryReqVO entry : entries) {
            if (NodeLogPolicy.isRoutineNoise(entry.getLevel(), entry.getComponent(), entry.getMessage())) continue;
            if (nodeLogMapper.selectByNodeAndEntry(nodeId, entry.getEntryId()) != null) {
                continue;
            }
            NodeLogDO value = BeanUtils.toBean(entry, NodeLogDO.class);
            value.setNodeId(nodeId);
            value.setMessage(SensitiveTextRedactor.redactText(entry.getMessage()));
            value.setContextJson(SensitiveTextRedactor.redactContext(entry.getContextJson()));
            value.setLoggedAt(normalizeTimestamp(entry.getTimestampMillis(), now));
            value.setCreator("edge-agent");
            value.setUpdater("edge-agent");
            try {
                nodeLogMapper.insert(value);
            } catch (DuplicateKeyException ignored) {
                // Retried batches are idempotent by tenant/node/entryId.
            }
        }
    }

    @Override
    public int cleanupExpiredLogs() {
        LocalDateTime now = LocalDateTime.now();
        String[] levels = {"ERROR", "WARN", "INFO", "DEBUG"};
        int[] days = {logProperties.getErrorRetentionDays(), logProperties.getWarnRetentionDays(),
                logProperties.getInfoRetentionDays(), logProperties.getDebugRetentionDays()};
        int total = 0;
        // Each severity gets a bounded budget so heavy INFO traffic cannot starve others.
        for (int index = 0; index < levels.length; index++) {
            for (int batch = 0; batch < logProperties.getCleanupMaxBatches(); batch++) {
                int deleted = nodeLogMapper.deleteExpiredGlobal(levels[index], now.minusDays(days[index]),
                        logProperties.getCleanupBatchSize());
                total += deleted;
                if (deleted < logProperties.getCleanupBatchSize()) break;
            }
        }
        return total;
    }

    @Override
    public PageResult<NodeLogRespVO> getPage(NodeLogPageReqVO reqVO) {
        PageResult<NodeLogDO> page = nodeLogMapper.selectPage(reqVO, reqVO.getNodeId(), reqVO.getTaskId(),
                reqVO.getComponent(), reqVO.getLevel(), reqVO.getKeyword(),
                reqVO.getDiagnosticId(), reqVO.getLoggedAt(), reqVO.getSnapshotMaxId(), reqVO.getAfterId());
        return new PageResult<>(BeanUtils.toBean(page.getList(), NodeLogRespVO.class),
                page.getTotal());
    }

    @Override
    public Long getSnapshotMaxId(Long nodeId) {
        var latest = nodeLogMapper.selectOne(new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<NodeLogDO>()
                .select(NodeLogDO::getId).eq(NodeLogDO::getNodeId, nodeId).orderByDesc(NodeLogDO::getId).last("LIMIT 1"));
        return latest == null ? 0L : latest.getId();
    }

    @Override
    public List<NodeLogRespVO> getContext(Long id, int before, int after) {
        NodeLogDO current = nodeLogMapper.selectById(id);
        if (current == null) {
            throw exception(NODE_LOG_NOT_FOUND);
        }
        List<NodeLogDO> previous = new ArrayList<>(nodeLogMapper.selectBefore(
                current.getNodeId(), id, Math.min(before, 100)));
        Collections.reverse(previous);
        previous.add(current);
        previous.addAll(nodeLogMapper.selectAfter(current.getNodeId(), id, Math.min(after, 100)));
        return BeanUtils.toBean(previous, NodeLogRespVO.class);
    }

    @Override
    public Long createDiagnostic(NodeDiagnosticCreateReqVO reqVO) {
        nodeService.validateNodeExists(reqVO.getNodeId());
        validateRange(reqVO.getRangeStart(), reqVO.getRangeEnd());
        NodeDiagnosticBundleDO value = BeanUtils.toBean(reqVO, NodeDiagnosticBundleDO.class);
        value.setStatus("QUEUED");
        value.setLogCount(0);
        value.setExpiresAt(LocalDateTime.now().plusHours(24));
        diagnosticMapper.insert(value);
        return value.getId();
    }

    @Override
    public NodeDiagnosticRespVO getDiagnostic(Long id) {
        NodeDiagnosticBundleDO value = diagnosticMapper.selectById(id);
        if (value == null) {
            throw exception(NODE_DIAGNOSTIC_NOT_FOUND);
        }
        return toDiagnosticResponse(value);
    }

    @Override
    public List<NodeDiagnosticRespVO> getDiagnostics(Long nodeId) {
        nodeService.validateNodeExists(nodeId);
        return diagnosticMapper.selectByNodeId(nodeId).stream()
                .map(this::toDiagnosticResponse)
                .toList();
    }

    @Override
    public List<NodeDiagnosticBundleDO> getQueuedDiagnosticsGlobal() {
        return diagnosticMapper.selectQueuedGlobal();
    }

    @Override
    public void buildDiagnostic(Long id) {
        NodeDiagnosticBundleDO bundle = diagnosticMapper.selectById(id);
        if (bundle == null || !"QUEUED".equals(bundle.getStatus())) {
            return;
        }
        bundle.setStatus("RUNNING");
        diagnosticMapper.updateById(bundle);
        try {
            EdgeNodeDO node = edgeNodeMapper.selectById(bundle.getNodeId());
            if (node == null) {
                throw exception(NODE_DIAGNOSTIC_NOT_FOUND);
            }
            List<NodeLogDO> logs = nodeLogMapper.selectForDiagnostic(bundle.getNodeId(),
                    bundle.getTaskId(), bundle.getRangeStart(), bundle.getRangeEnd());
            byte[] content = createZip(bundle, node, logs);
            String fileName = "linsight-diagnostic-node-" + bundle.getNodeId()
                    + "-" + bundle.getId() + ".zip";
            String fileRef = fileApi.createFile(content, fileName,
                    "ai-video/diagnostics/" + bundle.getNodeId(), "application/zip");
            bundle.setStatus("READY");
            bundle.setFileRef(fileRef);
            bundle.setFileName(fileName);
            bundle.setLogCount(logs.size());
            bundle.setExpiresAt(LocalDateTime.now().plusHours(24));
            bundle.setErrorMessage(null);
        } catch (RuntimeException | IOException error) {
            bundle.setStatus("FAILED");
            bundle.setErrorMessage("DiagnosticBuildFailed:" + error.getClass().getSimpleName());
        }
        diagnosticMapper.updateById(bundle);
    }

    private NodeDiagnosticRespVO toDiagnosticResponse(NodeDiagnosticBundleDO value) {
        NodeDiagnosticRespVO result = BeanUtils.toBean(value, NodeDiagnosticRespVO.class);
        if ("READY".equals(value.getStatus()) && value.getFileRef() != null
                && value.getExpiresAt().isAfter(LocalDateTime.now())) {
            result.setAccessUrl(fileApi.presignGetUrl(value.getFileRef(), DOWNLOAD_TTL_SECONDS)
                    .getCheckedData());
        }
        return result;
    }

    private static LocalDateTime normalizeTimestamp(Long timestampMillis, LocalDateTime now) {
        LocalDateTime value = LocalDateTime.ofInstant(Instant.ofEpochMilli(timestampMillis),
                ZoneId.systemDefault());
        if (value.isBefore(now.minusDays(7)) || value.isAfter(now.plusMinutes(5))) {
            return now;
        }
        return value;
    }

    private static void validateRange(LocalDateTime start, LocalDateTime end) {
        LocalDateTime now = LocalDateTime.now();
        if (!end.isAfter(start) || Duration.between(start, end).compareTo(Duration.ofHours(24)) > 0
                || start.isBefore(now.minusDays(7)) || end.isAfter(now.plusMinutes(5))) {
            throw exception(NODE_DIAGNOSTIC_RANGE_INVALID);
        }
    }

    private static byte[] createZip(NodeDiagnosticBundleDO bundle, EdgeNodeDO node,
                                    List<NodeLogDO> logs) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        try (ZipOutputStream zip = new ZipOutputStream(output, StandardCharsets.UTF_8)) {
            Map<String, Object> manifest = new LinkedHashMap<>();
            manifest.put("schemaVersion", "1.0");
            manifest.put("nodeId", node.getId());
            manifest.put("nodeCode", node.getCode());
            manifest.put("agentVersion", node.getAgentVersion());
            manifest.put("taskId", bundle.getTaskId());
            manifest.put("rangeStart", bundle.getRangeStart());
            manifest.put("rangeEnd", bundle.getRangeEnd());
            manifest.put("resourceSnapshot", node.getResourceSnapshot());
            manifest.put("logCount", logs.size());
            writeEntry(zip, "manifest.json", JsonUtils.toJsonPrettyString(manifest));
            StringBuilder lines = new StringBuilder();
            logs.forEach(log -> lines.append(JsonUtils.toJsonString(log)).append('\n'));
            writeEntry(zip, "logs.ndjson", lines.toString());
        }
        return output.toByteArray();
    }

    private static void writeEntry(ZipOutputStream zip, String name, String content)
            throws IOException {
        zip.putNextEntry(new ZipEntry(name));
        zip.write(content.getBytes(StandardCharsets.UTF_8));
        zip.closeEntry();
    }
}
