package com.linsight.module.aivideo.service.task;
import cn.hutool.crypto.digest.DigestUtil;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.module.aivideo.controller.admin.task.vo.FaceVerificationCreateReqVO;
import com.linsight.module.aivideo.controller.admin.task.vo.FaceVerificationRespVO;
import com.linsight.module.aivideo.dal.dataobject.task.FaceVerificationDO;
import com.linsight.module.aivideo.dal.mysql.task.FaceVerificationMapper;
import com.linsight.module.aivideo.framework.file.UploadContentValidator;
import com.linsight.module.aivideo.service.camera.CameraService;
import com.linsight.module.aivideo.service.model.ModelExecutionService;
import com.linsight.module.aivideo.service.node.NodeService;
import com.linsight.module.aivideo.service.node.NodeCommandDTO;
import com.linsight.module.aivideo.service.node.NodeCommandService;
import com.linsight.module.infra.api.file.FileApi;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import java.io.IOException;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import static com.linsight.framework.common.exception.util.ServiceExceptionUtil.exception;
import static com.linsight.module.aivideo.enums.task.ErrorCodeConstants.*;

/** Explicit developer verification sessions; no unattended identity search or access decision. */
@Service
public class FaceVerificationService {
    @Resource private FaceVerificationMapper mapper;
    @Resource private CameraService cameraService;
    @Resource private ModelExecutionService modelExecutionService;
    @Resource private NodeService nodeService;
    @Resource private NodeCommandService nodeCommandService;
    @Resource private FileApi fileApi;
    @Resource private TransactionTemplate transactionTemplate;

    public Long create(FaceVerificationCreateReqVO request) throws IOException {
        if (!Boolean.TRUE.equals(request.getConsentConfirmed())
                || request.getRoiX().add(request.getRoiWidth()).doubleValue() > 1
                || request.getRoiY().add(request.getRoiHeight()).doubleValue() > 1) {
            throw exception(TASK_CONFIG_INVALID);
        }
        cameraService.getRuntimeStreamUrl(request.getCameraId(), "SUB");
        nodeService.validateNodeAvailable(request.getNodeId());
        modelExecutionService.validateFaceVerificationReady(request.getModelVersionId(), request.getNodeId());
        byte[] content = request.getFile().getBytes();
        if (content.length == 0 || content.length > 10 * 1024 * 1024
                || UploadContentValidator.detectImageContentType(content) == null) {
            throw exception(TASK_CONFIG_INVALID);
        }
        String reference = fileApi.createFile(content, "reference-image",
                "ai-video/face-verification", UploadContentValidator.detectImageContentType(content));
        Map<String, Object> parameters = Map.of("schemaVersion", "1.0", "validationOnly", true,
                "consentConfirmed", true, "similarityThreshold", request.getSimilarityThreshold(),
                "temporalN", 3, "temporalM", 5,
                "roi", Map.of("x", request.getRoiX(), "y", request.getRoiY(),
                    "width", request.getRoiWidth(), "height", request.getRoiHeight()));
        return transactionTemplate.execute(status -> {
            FaceVerificationDO value = new FaceVerificationDO();
            value.setCameraId(request.getCameraId()); value.setNodeId(request.getNodeId());
            value.setModelVersionId(request.getModelVersionId());
            value.setReferenceRef(reference); value.setReferenceSha256(DigestUtil.sha256Hex(content));
            value.setParameters(JsonUtils.toJsonString(parameters)); value.setStatus("QUEUED");
            value.setCommandId(UUID.randomUUID().toString());
            value.setExpiresTime(LocalDateTime.now().plusSeconds(30)); mapper.insert(value);
            nodeCommandService.createCommand(value.getCommandId(), value.getNodeId(), "VERIFY_FACE",
                    value.getId(), 1, "face-verification:" + value.getId());
            return value.getId();
        });
    }

    public FaceVerificationRespVO get(Long id) {
        var value = require(id);
        var response = new FaceVerificationRespVO(); response.setId(id);
        response.setStatus(Set.of("QUEUED", "RUNNING").contains(value.getStatus())
                && value.getExpiresTime().isBefore(LocalDateTime.now()) ? "EXPIRED" : value.getStatus());
        response.setResult(value.getResult() == null ? Map.of() : JsonUtils.parseMap(value.getResult()));
        return response;
    }

    public Map<String, Object> command(String commandId, Long nodeId) {
        var command = nodeCommandService.getCommandForNode(commandId, nodeId);
        if (!"VERIFY_FACE".equals(command.getCommandType())) throw exception(TASK_NOT_FOUND);
        var value = require(command.getAggregateId());
        if (!value.getNodeId().equals(nodeId) || !value.getCommandId().equals(commandId)
                || !value.getExpiresTime().isAfter(LocalDateTime.now())) throw exception(TASK_STATUS_INVALID);
        Map<String, Object> result = new LinkedHashMap<>(JsonUtils.parseMap(value.getParameters()));
        result.put("sessionId", commandId); result.put("cameraId", value.getCameraId());
        result.put("modelVersionId", value.getModelVersionId());
        result.put("expiresAtMillis", value.getExpiresTime().atZone(ZoneId.systemDefault()).toInstant().toEpochMilli());
        result.put("sourceUrl", cameraService.getRuntimeStreamUrl(value.getCameraId(), "SUB"));
        result.put("referenceUrl", fileApi.presignGetUrl(value.getReferenceRef(), 60).getCheckedData());
        result.put("referenceSha256", value.getReferenceSha256());
        return result;
    }

    public void applyReport(NodeCommandDTO report) {
        if (!"VERIFY_FACE".equals(report.getCommandType())) return;
        var value = require(report.getAggregateId());
        if (!value.getNodeId().equals(report.getNodeId())
                || !value.getCommandId().equals(report.getCommandId())) throw exception(TASK_REPORT_STALE);
        value.setStatus(report.getStatus());
        if (report.getResult() != null) {
            Map<String, Object> result = new LinkedHashMap<>();
            for (String key : Set.of("status", "reason", "sampledFrames", "matchedFrames", "similarity",
                    "backend", "device", "liveness", "validationOnly")) {
                if (report.getResult().containsKey(key)) result.put(key, report.getResult().get(key));
            }
            value.setResult(JsonUtils.toJsonString(result));
        }
        mapper.updateById(value);
    }

    private FaceVerificationDO require(Long id) {
        var value = mapper.selectById(id);
        if (value == null) throw exception(TASK_NOT_FOUND);
        return value;
    }
}
