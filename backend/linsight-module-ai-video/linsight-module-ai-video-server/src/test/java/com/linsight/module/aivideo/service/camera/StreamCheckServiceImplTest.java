package com.linsight.module.aivideo.service.camera;

import com.linsight.framework.common.exception.ServiceException;
import com.linsight.module.aivideo.controller.node.camera.vo.StreamCheckReportReqVO;
import com.linsight.module.aivideo.controller.node.camera.vo.StreamCheckTaskRespVO;
import com.linsight.module.aivideo.dal.dataobject.camera.CameraDO;
import com.linsight.module.aivideo.dal.dataobject.camera.CameraStreamCheckDO;
import com.linsight.module.aivideo.dal.mysql.camera.CameraMapper;
import com.linsight.module.aivideo.dal.mysql.camera.CameraStreamCheckMapper;
import com.linsight.module.aivideo.service.node.NodeService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.LocalDateTime;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class StreamCheckServiceImplTest {

    @Mock
    private CameraStreamCheckMapper streamCheckMapper;
    @Mock
    private CameraMapper cameraMapper;
    @Mock
    private NodeService nodeService;
    @InjectMocks
    private StreamCheckServiceImpl streamCheckService;

    @Test
    void createMustValidateCameraAndExplicitNode() {
        when(cameraMapper.selectById(1L)).thenReturn(camera());
        doAnswer(invocation -> {
            invocation.<CameraStreamCheckDO>getArgument(0).setId(20L);
            return 1;
        }).when(streamCheckMapper).insert(any(CameraStreamCheckDO.class));

        Long id = streamCheckService.createStreamCheck(1L, 9L);

        assertEquals(20L, id);
        verify(nodeService).validateNodeAvailable(9L);
        verify(streamCheckMapper).insert(argThat((CameraStreamCheckDO check) -> check.getCameraId() == 1L
                && check.getNodeId() == 9L && "QUEUED".equals(check.getStatus())));
    }

    @Test
    void claimMustOnlyReturnTaskAssignedToAuthenticatedNode() {
        CameraStreamCheckDO check = runningCheck();
        check.setStatus("QUEUED");
        when(streamCheckMapper.selectFirstQueued(9L)).thenReturn(check);
        when(streamCheckMapper.claim(20L)).thenReturn(1);
        when(cameraMapper.selectById(1L)).thenReturn(camera());

        StreamCheckTaskRespVO result = streamCheckService.claimStreamCheck(9L);

        assertEquals(20L, result.getCheckId());
        assertEquals("/live/main", result.getStreamUri());
        assertEquals("secret-password", result.getPassword());
        verify(streamCheckMapper).selectFirstQueued(9L);
    }

    @Test
    void reportMustUpdateCheckAndCameraWithSanitizedFailure() {
        when(streamCheckMapper.selectById(20L)).thenReturn(runningCheck());
        StreamCheckReportReqVO report = report(false);
        report.setErrorCode("AUTH_FAILED");
        report.setErrorMessage("设备认证失败");

        streamCheckService.reportStreamCheck(9L, report);

        verify(streamCheckMapper).updateById(argThat((CameraStreamCheckDO check) -> "FAILED".equals(check.getStatus())
                && "AUTH_FAILED".equals(check.getErrorCode()) && check.getFinishTime() != null));
        verify(cameraMapper).updateStreamCheckStatus(eq(1L), eq(2), any(LocalDateTime.class),
                eq("AUTH_FAILED"), eq("设备认证失败"));
    }

    @Test
    void reportMustRejectDifferentNode() {
        when(streamCheckMapper.selectById(20L)).thenReturn(runningCheck());

        ServiceException exception = assertThrows(ServiceException.class,
                () -> streamCheckService.reportStreamCheck(8L, report(true)));

        assertEquals(1_020_000_112, exception.getCode());
        verify(streamCheckMapper, never()).updateById(any(CameraStreamCheckDO.class));
        verify(cameraMapper, never()).updateStreamCheckStatus(anyLong(), anyInt(), any(), any(), any());
    }

    private static CameraDO camera() {
        CameraDO camera = new CameraDO();
        camera.setId(1L);
        camera.setProtocol("RTSP");
        camera.setHost("192.0.2.10");
        camera.setPort(554);
        camera.setMainStreamUri("/live/main");
        camera.setUsername("operator");
        camera.setPassword("secret-password");
        return camera;
    }

    private static CameraStreamCheckDO runningCheck() {
        CameraStreamCheckDO check = new CameraStreamCheckDO();
        check.setId(20L);
        check.setCameraId(1L);
        check.setNodeId(9L);
        check.setStatus("RUNNING");
        return check;
    }

    private static StreamCheckReportReqVO report(boolean online) {
        StreamCheckReportReqVO report = new StreamCheckReportReqVO();
        report.setCheckId(20L);
        report.setOnline(online);
        report.setDiagnosticId("00000000-0000-0000-0000-000000000001");
        report.setStages(java.util.List.of());
        return report;
    }

}
