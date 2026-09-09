package com.linsight.module.aivideo.service.camera;
import com.linsight.module.aivideo.dal.mysql.camera.CameraDisplayPreferenceMapper;
import com.linsight.module.aivideo.dal.dataobject.camera.CameraDO;
import com.linsight.module.aivideo.dal.dataobject.camera.CameraDisplayPreferenceDO;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.*;
import org.mockito.junit.jupiter.MockitoExtension;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
@ExtendWith(MockitoExtension.class)
class CameraDisplayPreferenceServiceTest {
 @Mock CameraDisplayPreferenceMapper mapper;
 @Mock CameraService cameraService;
 @InjectMocks CameraDisplayPreferenceService service;
 @Test void newPreferenceIsOwnedByUserAndDoesNotChangeTasks() {
  when(cameraService.getCamera(7L)).thenReturn(new CameraDO());
  assertEquals(List.of(),service.get(9L,7L));
  service.save(9L,7L,List.of("task-11","task-11","entry-1"));
  var capture=ArgumentCaptor.forClass(CameraDisplayPreferenceDO.class);verify(mapper).insert(capture.capture());
  assertEquals(9L,capture.getValue().getUserId());assertEquals(7L,capture.getValue().getCameraId());
  assertEquals("[\"task-11\",\"entry-1\"]",capture.getValue().getHiddenLayersJson());
 }
 @Test void missingOrOtherTenantCameraCannotReceivePreferences() {
  assertThrows(RuntimeException.class,()->service.save(9L,77L,List.of("task-11")));
  verifyNoInteractions(mapper);
 }
}
