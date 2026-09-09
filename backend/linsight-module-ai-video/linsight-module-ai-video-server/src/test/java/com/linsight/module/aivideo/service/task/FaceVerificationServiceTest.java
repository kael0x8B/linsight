package com.linsight.module.aivideo.service.task;

import com.linsight.framework.common.exception.ServiceException;
import com.linsight.module.aivideo.controller.admin.task.vo.FaceVerificationCreateReqVO;
import com.linsight.module.aivideo.dal.dataobject.task.FaceVerificationDO;
import com.linsight.module.aivideo.dal.mysql.task.FaceVerificationMapper;
import com.linsight.module.aivideo.service.camera.CameraService;
import com.linsight.module.aivideo.service.model.ModelExecutionService;
import com.linsight.module.aivideo.service.node.NodeCommandDTO;
import com.linsight.module.aivideo.service.node.NodeCommandService;
import com.linsight.module.infra.api.file.FileApi;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class FaceVerificationServiceTest {
    @Mock private FaceVerificationMapper mapper;
    @Mock private NodeCommandService nodeCommandService;
    @Mock private CameraService cameraService;
    @Mock private ModelExecutionService modelExecutionService;
    @Mock private FileApi fileApi;
    @InjectMocks private FaceVerificationService service;

    @Test void noConsentDoesNotReadCameraOrUploadImage() {
        var request = new FaceVerificationCreateReqVO(); request.setConsentConfirmed(false);
        assertThrows(ServiceException.class, () -> service.create(request));
        verifyNoInteractions(cameraService, modelExecutionService, fileApi, mapper);
    }
    @Test void outOfBoundsRoiDoesNotStartCamera() {
        var request = new FaceVerificationCreateReqVO(); request.setConsentConfirmed(true);
        request.setRoiX(new BigDecimal("0.9")); request.setRoiWidth(new BigDecimal("0.2"));
        assertThrows(ServiceException.class, () -> service.create(request));
        verifyNoInteractions(cameraService, modelExecutionService, fileApi, mapper);
    }
    @Test void queryNeverExposesReferenceOrCredentials() {
        var row = row(); row.setReferenceRef("private-object");
        row.setResult("{\"status\":\"MATCH\",\"device\":\"CPU\"}");
        when(mapper.selectById(1L)).thenReturn(row);
        var response = service.get(1L);
        assertEquals("QUEUED", response.getStatus()); assertEquals("CPU", response.getResult().get("device"));
        verifyNoInteractions(fileApi);
    }
    @Test void expiredCommandDoesNotIssuePhotoUrlOrCameraCredentials() {
        var row = row(); row.setExpiresTime(LocalDateTime.now().minusSeconds(1));
        when(nodeCommandService.getCommandForNode("command", 2L)).thenReturn(command());
        when(mapper.selectById(1L)).thenReturn(row);
        assertThrows(ServiceException.class, () -> service.command("command", 2L));
        verifyNoInteractions(fileApi, cameraService);
    }
    @Test void wrongNodeReportCannotChangeSession() {
        var report = command(); report.setNodeId(3L);
        when(mapper.selectById(1L)).thenReturn(row());
        assertThrows(ServiceException.class, () -> service.applyReport(report));
        verify(mapper, never()).updateById(any(FaceVerificationDO.class));
    }
    @Test void reportRetainsOnlyBoundedPublicResultFields() {
        var row = row(); var report = command(); report.setStatus("SUCCEEDED");
        report.setResult(Map.of("status", "MATCH", "device", "CPU", "referenceUrl", "secret", "feature", "secret"));
        when(mapper.selectById(1L)).thenReturn(row);
        service.applyReport(report);
        assertFalse(row.getResult().contains("secret")); assertTrue(row.getResult().contains("MATCH"));
    }
    private FaceVerificationDO row() {
        var row = new FaceVerificationDO(); row.setId(1L); row.setNodeId(2L); row.setCommandId("command");
        row.setStatus("QUEUED"); row.setExpiresTime(LocalDateTime.now().plusSeconds(30)); return row;
    }
    private NodeCommandDTO command() {
        var command = new NodeCommandDTO(); command.setAggregateId(1L); command.setNodeId(2L);
        command.setCommandId("command"); command.setCommandType("VERIFY_FACE"); return command;
    }
}
