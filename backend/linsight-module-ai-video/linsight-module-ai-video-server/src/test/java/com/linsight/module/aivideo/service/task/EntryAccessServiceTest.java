package com.linsight.module.aivideo.service.task;
import com.linsight.framework.common.exception.ServiceException;
import com.linsight.module.aivideo.dal.dataobject.task.*;
import com.linsight.module.aivideo.dal.mysql.task.*;
import com.linsight.module.aivideo.service.algorithm.*;
import com.linsight.module.aivideo.service.event.*;
import com.linsight.module.aivideo.service.node.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.*;
import org.mockito.junit.jupiter.MockitoExtension;
import java.time.LocalDateTime;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
@ExtendWith(MockitoExtension.class)
class EntryAccessServiceTest {
 @Mock EntryAccessMapper entryMapper; @Mock EntryScanMapper scanMapper;
 @Mock FaceReferenceService references; @Mock NodeCommandService commands; @Mock EventService events;
 @Mock NodeService nodes;
 @Mock com.linsight.module.aivideo.service.camera.CameraService cameras;
 @Mock com.linsight.module.aivideo.service.model.ModelExecutionService models;
 @Mock org.springframework.transaction.support.TransactionTemplate transactions;
 @InjectMocks EntryAccessService service;
 EntryScanDO row; NodeCommandDTO report;
 void setup(boolean allowed) {
  row=new EntryScanDO();row.setId(1L);row.setEntryAccessId(2L);row.setCameraId(3L);row.setNodeId(4L);
  row.setModelVersionId(5L);row.setCommandId("command");row.setMode("IDENTIFY");row.setStatus("RUNNING");
  row.setExpiresTime(LocalDateTime.now().plusSeconds(60));
  row.setSnapshot("{\"version\":1,\"libraryId\":6,\"referenceIds\":[7],\"allowedEntryIds\":"+(allowed?"[8]":"[]")+",\"temporalN\":3,\"temporalM\":5,\"similarityThreshold\":0.6}");
  report=new NodeCommandDTO();report.setCommandType("ENTRY_FACE");report.setCommandId("command");report.setAggregateId(1L);
  report.setNodeId(4L);report.setStatus("SUCCEEDED");when(scanMapper.selectOne(any())).thenReturn(row);
 }
 void live(boolean valid) {
  when(scanMapper.selectById(1L)).thenReturn(row);when(commands.getCommandForNode("command",4L)).thenReturn(report);
  var e=new EntryAccessDO();e.setId(2L);e.setEnabled(true);e.setVersion(1);when(entryMapper.selectById(2L)).thenReturn(e);
  if(valid){var r=new FaceReferenceDTO();r.setId(7L);r.setEntryId(8L);r.setName("Synthetic fixture");r.setExternalCode("TEST");when(references.ready(6L,5L)).thenReturn(List.of(r));}
 }
 void matching(){report.setResult(Map.of("status","MATCH","entryId",8,"matchedFrames",3,"sampledFrames",5,"device","RKNPU","similarity",.8));}
 @Test void authorizedDoesNotAlarm(){setup(true);live(true);matching();service.applyReport(report);assertTrue(row.getResult().contains("AUTHORIZED"));verifyNoInteractions(events);}
 @Test void deniedIsIdempotent(){setup(false);live(true);matching();when(events.createEntryAccessEvent(any())).thenReturn(99L);service.applyReport(report);service.applyReport(report);assertEquals(99L,row.getEventId());verify(events,times(1)).createEntryAccessEvent(argThat(v->v.getResult().get("decision").equals("PERMISSION_DENIED")));}
 @Test void unknownNeedsEnoughFrames(){setup(false);live(true);report.setResult(Map.of("status","IDENTITY_UNCONFIRMED","matchedFrames",1,"sampledFrames",5));service.applyReport(report);verifyNoInteractions(events);}
 @Test void confirmedUnknownRaisesReviewEvent(){setup(false);live(true);report.setResult(Map.of("status","IDENTITY_UNCONFIRMED","matchedFrames",3,"sampledFrames",5));service.applyReport(report);verify(events).createEntryAccessEvent(argThat(v->v.getResult().get("decision").equals("IDENTITY_UNCONFIRMED")));}
 @Test void revokedCannotAuthorize(){setup(true);live(false);matching();service.applyReport(report);assertTrue(row.getResult().contains("CANCELLED"));verifyNoInteractions(events);}
 @Test void cancelledIgnoresLateResult(){setup(false);row.setStatus("CANCELLED");matching();service.applyReport(report);verifyNoInteractions(events,references);}
 @Test void wrongNodeRejected(){setup(false);report.setNodeId(99L);matching();assertThrows(ServiceException.class,()->service.applyReport(report));verifyNoInteractions(events);}
 @Test void enrollmentDoesNotExposeRawPrivateData(){setup(false);row.setMode("ENROLL");row.setReferenceId(7L);report.setResult(Map.of("status","REFERENCE_READY","feature","must-not-persist","referenceUrl","private"));service.applyReport(report);verify(references).applyValidation(eq(7L),eq("command"),eq(true),anyMap());verifyNoInteractions(events);assertFalse(row.getResult().contains("private"));assertFalse(row.getResult().contains("must-not-persist"));}

 @Test void extractionRequiresConsentBeforeAnyNodeOrPhotoWork() {
  var request=new com.linsight.module.aivideo.controller.admin.task.vo.FaceExtractionReqVO();request.setConsentConfirmed(false);
  assertThrows(ServiceException.class,()->service.extract(request));verifyNoInteractions(nodes,models,references,commands);
 }
 @Test void existingExtractionIssuesDurableEnrollmentForSameReference() {
  var request=new com.linsight.module.aivideo.controller.admin.task.vo.FaceExtractionReqVO();
  request.setEntryId(8L);request.setNodeId(1L);request.setModelVersionId(131L);request.setConsentConfirmed(true);request.setValidUntil(LocalDateTime.now().plusDays(1));
  var photo=new FaceReferenceService.ExistingPhoto(8L,"object","hash");when(references.prepareExistingPhoto(8L)).thenReturn(photo);
  when(references.registerExisting(eq(photo),eq(131L),eq(request.getValidUntil()),anyString())).thenReturn(77L);
  when(transactions.execute(any())).thenAnswer(invocation->((org.springframework.transaction.support.TransactionCallback<?>)invocation.getArgument(0)).doInTransaction(null));
  doAnswer(invocation->{((EntryScanDO)invocation.getArgument(0)).setId(99L);return 1;}).when(scanMapper).insert(any(EntryScanDO.class));
  assertEquals(99L,service.extract(request));
  verify(nodes).validateNodeAvailable(1L);verify(models).validateFaceVerificationReady(131L,1L);
  verify(scanMapper).insert(argThat((EntryScanDO s)->s.getReferenceId()==77L&&s.getCameraId()==0L&&s.getMode().equals("ENROLL")));
  verifyNoInteractions(entryMapper,events);
 }

 private com.linsight.module.aivideo.controller.admin.task.vo.EntryAccessSaveReqVO configuration(Long id, long nodeId) {
  var r=new com.linsight.module.aivideo.controller.admin.task.vo.EntryAccessSaveReqVO();
  r.setId(id);r.setNodeId(nodeId);r.setCameraId(3L);r.setVersion(1);r.setName("Entrance");
  r.setLibraryId(6L);r.setModelVersionId(131L);r.setEnabled(false);r.setTriggerMode("FACE_ZONE");
  r.setTemporalN(3);r.setTemporalM(5);r.setRoiX(.25);r.setRoiY(.1);r.setRoiWidth(.5);r.setRoiHeight(.8);
  r.setSimilarityThreshold(.6);r.setAmbiguityMargin(.08);r.setAllowedEntryIds(List.of());return r;
 }
 private EntryAccessDO entrance(long id,long nodeId) {
  var e=new EntryAccessDO();e.setId(id);e.setNodeId(nodeId);e.setCameraId(3L);e.setVersion(1);e.setEnabled(false);return e;
 }
 @Test void editingCannotMoveEntranceToAnotherGatewayOrCamera() {
  when(entryMapper.selectById(2L)).thenReturn(entrance(2,4));
  assertThrows(ServiceException.class,()->service.save(configuration(2L,5)));
  var wrongCamera=configuration(2L,4);wrongCamera.setCameraId(99L);
  assertThrows(ServiceException.class,()->service.save(wrongCamera));
  verifyNoInteractions(cameras,models,references);verify(entryMapper,never()).update(any(),any());
 }
 @Test void sameCameraCanHaveSeparateConfigurationsOnTwoGateways() {
  when(references.ready(6L,131L)).thenReturn(List.of());
  doAnswer(i->{var e=(EntryAccessDO)i.getArgument(0);e.setId(e.getNodeId()+100);return 1;}).when(entryMapper).insert(any(EntryAccessDO.class));
  assertEquals(104L,service.save(configuration(null,4)));assertEquals(105L,service.save(configuration(null,5)));
  verify(models).validateFaceVerificationReady(131L,4L);verify(models).validateFaceVerificationReady(131L,5L);
  verify(entryMapper).insert(argThat((EntryAccessDO e)->e.getNodeId()==4L&&e.getCameraId()==3L));
  verify(entryMapper).insert(argThat((EntryAccessDO e)->e.getNodeId()==5L&&e.getCameraId()==3L));
 }
 @Test void scopedOperationsRejectOtherGatewayWithoutChangingAnything() {
  when(entryMapper.selectById(2L)).thenReturn(entrance(2,4));
  assertThrows(ServiceException.class,()->service.stop(2L,5L));
  assertThrows(ServiceException.class,()->service.enable(2L,5L));
  assertThrows(ServiceException.class,()->service.delete(2L,5L));
  assertThrows(ServiceException.class,()->service.stationStatus(2L,5L));
  verifyNoInteractions(scanMapper,commands,models,references);
  verify(entryMapper,never()).updateById(any(EntryAccessDO.class));verify(entryMapper,never()).deleteById(any(java.io.Serializable.class));
 }
 @Test void stoppingOneGatewayKeepsOtherGatewayConfiguration() {
  var current=entrance(2,4);current.setEnabled(true);
  when(entryMapper.selectById(2L)).thenReturn(current);when(scanMapper.selectList(any())).thenReturn(List.of());
  service.stop(2L,4L);assertFalse(current.getEnabled());assertEquals(2,current.getVersion());
  verify(entryMapper).updateById(argThat((EntryAccessDO e)->e.getId()==2L&&e.getNodeId()==4L));
  verify(entryMapper,never()).selectById(3L);
 }
}
