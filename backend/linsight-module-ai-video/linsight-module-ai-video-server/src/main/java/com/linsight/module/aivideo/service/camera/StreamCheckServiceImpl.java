package com.linsight.module.aivideo.service.camera;

import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.module.aivideo.controller.node.camera.vo.StreamCheckReportReqVO;
import com.linsight.module.aivideo.controller.node.camera.vo.StreamCheckTaskRespVO;
import com.linsight.module.aivideo.dal.dataobject.camera.CameraDO;
import com.linsight.module.aivideo.dal.dataobject.camera.CameraStreamCheckDO;
import com.linsight.module.aivideo.dal.mysql.camera.CameraMapper;
import com.linsight.module.aivideo.dal.mysql.camera.CameraStreamCheckMapper;
import com.linsight.module.aivideo.service.node.NodeService;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;

import java.time.LocalDateTime;
import java.util.Objects;

import static com.linsight.framework.common.exception.util.ServiceExceptionUtil.exception;
import static com.linsight.module.aivideo.enums.camera.ErrorCodeConstants.*;

@Service
@Validated
public class StreamCheckServiceImpl implements StreamCheckService {

    @Resource
    private CameraStreamCheckMapper streamCheckMapper;
    @Resource
    private CameraMapper cameraMapper;
    @Resource
    private NodeService nodeService;

    @Override
    public Long createStreamCheck(Long cameraId, Long nodeId) {
        if (cameraMapper.selectById(cameraId) == null) {
            throw exception(CAMERA_NOT_FOUND);
        }
        nodeService.validateNodeAvailable(nodeId);
        CameraStreamCheckDO check = new CameraStreamCheckDO();
        check.setCameraId(cameraId);
        check.setNodeId(nodeId);
        check.setStatus("QUEUED");
        streamCheckMapper.insert(check);
        return check.getId();
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public StreamCheckTaskRespVO claimStreamCheck(Long nodeId) {
        for (int attempt = 0; attempt < 3; attempt++) {
            CameraStreamCheckDO check = streamCheckMapper.selectFirstQueued(nodeId);
            if (check == null) {
                return null;
            }
            if (streamCheckMapper.claim(check.getId()) == 0) {
                continue;
            }
            CameraDO camera = cameraMapper.selectById(check.getCameraId());
            if (camera == null) {
                failMissingCamera(check);
                continue;
            }
            StreamCheckTaskRespVO task = new StreamCheckTaskRespVO();
            task.setCheckId(check.getId());
            task.setCameraId(camera.getId());
            task.setProtocol(camera.getProtocol());
            task.setHost(camera.getHost());
            task.setPort(camera.getPort());
            task.setStreamUri(camera.getMainStreamUri());
            task.setUsername(camera.getUsername());
            task.setPassword(camera.getPassword());
            return task;
        }
        return null;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void reportStreamCheck(Long nodeId, StreamCheckReportReqVO reqVO) {
        CameraStreamCheckDO check = validateCheck(reqVO.getCheckId());
        if (!Objects.equals(check.getNodeId(), nodeId)) {
            throw exception(CAMERA_STREAM_CHECK_NODE_MISMATCH);
        }
        if (!Objects.equals(check.getStatus(), "RUNNING")) {
            throw exception(CAMERA_STREAM_CHECK_STATE_INVALID);
        }
        LocalDateTime now = LocalDateTime.now();
        check.setStatus(Boolean.TRUE.equals(reqVO.getOnline()) ? "SUCCEEDED" : "FAILED");
        check.setDiagnosticId(reqVO.getDiagnosticId());
        check.setStageResults(JsonUtils.toJsonString(reqVO.getStages()));
        check.setStreamInfo(reqVO.getStream() == null ? null : JsonUtils.toJsonString(reqVO.getStream()));
        check.setErrorCode(reqVO.getErrorCode());
        check.setErrorMessage(reqVO.getErrorMessage());
        check.setFinishTime(now);
        check.setUpdater("edge-agent");
        streamCheckMapper.updateById(check);

        cameraMapper.updateStreamCheckStatus(check.getCameraId(),
                Boolean.TRUE.equals(reqVO.getOnline()) ? 1 : 2,
                now, reqVO.getErrorCode(), reqVO.getErrorMessage());
    }

    @Override
    public CameraStreamCheckDO getStreamCheck(Long id) {
        return validateCheck(id);
    }

    private CameraStreamCheckDO validateCheck(Long id) {
        CameraStreamCheckDO check = streamCheckMapper.selectById(id);
        if (check == null) {
            throw exception(CAMERA_STREAM_CHECK_NOT_FOUND);
        }
        return check;
    }

    private void failMissingCamera(CameraStreamCheckDO check) {
        check.setStatus("FAILED");
        check.setErrorCode("CAMERA_NOT_FOUND");
        check.setErrorMessage("摄像头已删除，检测未执行");
        check.setFinishTime(LocalDateTime.now());
        check.setUpdater("edge-agent");
        streamCheckMapper.updateById(check);
    }

}
