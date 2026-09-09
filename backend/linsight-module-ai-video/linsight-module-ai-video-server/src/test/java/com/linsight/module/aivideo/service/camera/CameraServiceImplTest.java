package com.linsight.module.aivideo.service.camera;

import com.linsight.framework.common.exception.ServiceException;
import com.linsight.module.aivideo.controller.admin.camera.vo.CameraRespVO;
import com.linsight.module.aivideo.controller.admin.camera.vo.CameraSaveReqVO;
import com.linsight.module.aivideo.convert.camera.CameraConvert;
import com.linsight.module.aivideo.dal.dataobject.camera.CameraDO;
import com.linsight.module.aivideo.dal.mysql.camera.CameraMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class CameraServiceImplTest {

    @Mock
    private CameraMapper cameraMapper;
    @Mock
    private CameraGroupService cameraGroupService;
    @InjectMocks
    private CameraServiceImpl cameraService;

    @Test
    void cameraConvertMustReturnMaskedEndpointWithoutSecretFields() {
        CameraDO camera = cameraDO();
        camera.setMainStreamUri("/live/main?token=secret");
        camera.setUsername("operator");
        camera.setPassword("secret-password");
        when(cameraMapper.selectById(1L)).thenReturn(camera);

        CameraRespVO result = CameraConvert.INSTANCE.convert(cameraService.getCamera(1L));

        assertEquals("rtsp://192.0.2.10:554/***", result.getMaskedStreamEndpoint());
        assertTrue(result.getCredentialConfigured());
        assertFalse(result.toString().contains("secret-password"));
        assertFalse(result.toString().contains("token=secret"));
    }

    @Test
    void updateCameraMustPreserveBlankCredentials() {
        CameraDO current = cameraDO();
        current.setVersion(3);
        when(cameraMapper.selectById(1L)).thenReturn(current);
        when(cameraMapper.selectByCode("CAM-001")).thenReturn(current);

        CameraSaveReqVO update = saveReqVO();
        update.setId(1L);
        update.setMainStreamUri(" ");
        update.setSubStreamUri("");
        update.setUsername(null);
        update.setPassword("");
        cameraService.updateCamera(update);

        ArgumentCaptor<CameraDO> captor = ArgumentCaptor.forClass(CameraDO.class);
        verify(cameraMapper).updateById(captor.capture());
        CameraDO persisted = captor.getValue();
        assertNull(persisted.getMainStreamUri());
        assertNull(persisted.getSubStreamUri());
        assertNull(persisted.getUsername());
        assertNull(persisted.getPassword());
        assertEquals(3, persisted.getVersion());
    }

    @Test
    void createCameraMustRejectMissingMainStream() {
        CameraSaveReqVO create = saveReqVO();
        create.setMainStreamUri(" ");

        ServiceException exception = assertThrows(ServiceException.class, () -> cameraService.createCamera(create));

        assertEquals(1_020_000_102, exception.getCode());
        verify(cameraMapper, never()).insert(any(CameraDO.class));
    }

    @Test
    void runtimeStreamUrlMustEncodeCredentialsAndKeepConfiguredHost() {
        CameraDO camera = cameraDO();
        camera.setMainStreamUri("rtsp://untrusted.example/private/live?profile=main");
        camera.setUsername("operator@example.com");
        camera.setPassword("p@ss word");
        when(cameraMapper.selectById(1L)).thenReturn(camera);

        String result = cameraService.getRuntimeStreamUrl(1L, "MAIN");

        assertEquals("rtsp://operator%40example.com:p%40ss%20word@192.0.2.10:554/private/live?profile=main",
                result);
    }

    @Test
    void runtimeSubStreamMustRejectMissingConfiguration() {
        when(cameraMapper.selectById(1L)).thenReturn(cameraDO());

        ServiceException exception = assertThrows(ServiceException.class,
                () -> cameraService.getRuntimeStreamUrl(1L, "SUB"));

        assertEquals(1_020_000_120, exception.getCode());
    }

    private static CameraDO cameraDO() {
        CameraDO camera = new CameraDO();
        camera.setId(1L);
        camera.setName("一号门岗");
        camera.setCode("CAM-001");
        camera.setGroupId(0L);
        camera.setProtocol("RTSP");
        camera.setHost("192.0.2.10");
        camera.setPort(554);
        camera.setStatus(0);
        camera.setOnlineStatus(0);
        camera.setVersion(1);
        return camera;
    }

    private static CameraSaveReqVO saveReqVO() {
        CameraSaveReqVO reqVO = new CameraSaveReqVO();
        reqVO.setName("一号门岗");
        reqVO.setCode("CAM-001");
        reqVO.setGroupId(0L);
        reqVO.setProtocol("RTSP");
        reqVO.setHost("192.0.2.10");
        reqVO.setPort(554);
        reqVO.setMainStreamUri("/live/main");
        reqVO.setStatus(0);
        return reqVO;
    }

}
