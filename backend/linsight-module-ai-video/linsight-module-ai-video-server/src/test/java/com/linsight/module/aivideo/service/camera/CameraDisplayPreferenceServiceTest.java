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
  service.save(9L,7L,List.of("task-11","task-11","entry-1","roi-task-11","roi-entry-1"));
  var capture=ArgumentCaptor.forClass(CameraDisplayPreferenceDO.class);verify(mapper).insert(capture.capture());
  assertEquals(9L,capture.getValue().getUserId());assertEquals(7L,capture.getValue().getCameraId());
  assertEquals("[\"task-11\",\"entry-1\",\"roi-task-11\",\"roi-entry-1\"]",capture.getValue().getHiddenLayersJson());
 }
 @Test void acceptsRegionDisplayPreferenceWithoutAcceptingArbitraryLayerKeys() {
  try(var factory=jakarta.validation.Validation.buildDefaultValidatorFactory()) {
   var value=new com.linsight.module.aivideo.controller.admin.camera.vo.CameraDisplayPreferenceSaveReqVO();
   value.setCameraId(7L);value.setHiddenLayers(List.of("recognition-regions","task-11","entry-1","roi-task-11","roi-entry-1"));
   assertTrue(factory.getValidator().validate(value).isEmpty());
   value.setHiddenLayers(List.of("unknown-layer"));
   assertFalse(factory.getValidator().validate(value).isEmpty());
   for (String invalid : List.of("roi-task-undefined", "roi-task--1", "roi-entry-abc", "roi-recognition-regions")) {
    value.setHiddenLayers(List.of(invalid));
    assertFalse(factory.getValidator().validate(value).isEmpty(), invalid);
   }
  }
 }
 @Test void missingOrOtherTenantCameraCannotReceivePreferences() {
  assertThrows(RuntimeException.class,()->service.save(9L,77L,List.of("task-11")));
  verifyNoInteractions(mapper);
 }
}
