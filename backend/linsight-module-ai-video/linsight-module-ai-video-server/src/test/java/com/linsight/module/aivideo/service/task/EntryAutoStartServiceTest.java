package com.linsight.module.aivideo.service.task;
import com.linsight.framework.common.exception.ServiceException;
import com.linsight.module.aivideo.dal.dataobject.task.*;
import com.linsight.module.aivideo.dal.mysql.task.*;
import com.linsight.module.aivideo.service.algorithm.*;
import com.linsight.module.aivideo.service.node.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.*;
import org.mockito.junit.jupiter.MockitoExtension;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
@ExtendWith(MockitoExtension.class)
class EntryAutoStartServiceTest {
 @Mock EntryAccessMapper entryMapper; @Mock EntryScanMapper scanMapper;
 @Mock FaceReferenceService references; @Mock NodeCommandService commands;
 @InjectMocks EntryAccessService service;
 EntryAccessDO entry; final String encounter=UUID.randomUUID().toString();
 @BeforeEach void setup(){entry=new EntryAccessDO();entry.setId(1L);entry.setNodeId(2L);entry.setCameraId(3L);entry.setModelVersionId(131L);entry.setLibraryId(4L);entry.setEnabled(true);entry.setVersion(5);entry.setName("Synthetic entrance");entry.setParameters("{\"triggerMode\":\"FACE_ZONE\"}");}
 void locked(){when(entryMapper.selectOne(any())).thenReturn(entry);}
 Long start(){return service.autoStart(1L,5,encounter,System.currentTimeMillis(),2L);}
 void roster(){var reference=new FaceReferenceDTO();reference.setId(7L);reference.setEntryId(8L);when(references.ready(4L,131L)).thenReturn(List.of(reference));}
 @Test void createsDurableCommandWithoutAdminStart(){locked();roster();when(scanMapper.selectCount(any())).thenReturn(0L);doAnswer(inv->{((EntryScanDO)inv.getArgument(0)).setId(99L);return 1;}).when(scanMapper).insert(any(EntryScanDO.class));assertEquals(99L,start());verify(commands).createCommand(encounter,2L,"ENTRY_FACE",99L,1,"entry-face:99");verify(scanMapper).insert(argThat((EntryScanDO s)->s.getSnapshot().contains("DESIGNATED_FACE_ZONE")&&s.getSnapshot().contains("referenceIds")));}
 @Test void duplicateEncounterReturnsOriginalWithoutSecondCommand(){locked();var scan=new EntryScanDO();scan.setId(99L);scan.setEntryAccessId(1L);scan.setNodeId(2L);when(scanMapper.selectOne(any())).thenReturn(scan);assertEquals(99L,start());verifyNoInteractions(commands,references);verify(scanMapper,never()).insert(any(EntryScanDO.class));}
 @Test void anotherNodeCannotTrigger(){locked();assertThrows(ServiceException.class,()->service.autoStart(1L,5,encounter,System.currentTimeMillis(),9L));verifyNoInteractions(scanMapper,commands,references);}
 @Test void stoppedEntranceCannotTrigger(){locked();entry.setEnabled(false);assertThrows(ServiceException.class,this::start);verifyNoInteractions(commands,references);}
 @Test void oldConfigCannotTrigger(){locked();assertThrows(ServiceException.class,()->service.autoStart(1L,4,encounter,System.currentTimeMillis(),2L));verifyNoInteractions(commands,references);}
 @Test void staleObservationCannotTrigger(){locked();assertThrows(ServiceException.class,()->service.autoStart(1L,5,encounter,System.currentTimeMillis()-20000,2L));verifyNoInteractions(commands,references);}
 @Test void manualEntranceCannotTrigger(){locked();entry.setParameters("{}");assertThrows(ServiceException.class,this::start);verifyNoInteractions(commands,references);}
 @Test void overlappingEncounterCannotTrigger(){locked();roster();when(scanMapper.selectCount(any())).thenReturn(1L);assertThrows(ServiceException.class,this::start);verifyNoInteractions(commands);}
 @Test void missingReferenceCannotTrigger(){locked();when(references.ready(4L,131L)).thenReturn(List.of());assertThrows(ServiceException.class,this::start);verifyNoInteractions(commands);}
 @Test void stationReportRequiresSameConfigAndOwner(){when(entryMapper.selectById(1L)).thenReturn(entry);assertThrows(ServiceException.class,()->service.reportStation(9L,1L,5,"READY"));assertThrows(ServiceException.class,()->service.reportStation(2L,1L,4,"READY"));assertThrows(ServiceException.class,()->service.reportStation(2L,1L,5,"invented"));service.reportStation(2L,1L,5,"READY");assertEquals("READY",service.stationStatus(1L).get("state"));entry.setVersion(6);assertEquals("OFFLINE",service.stationStatus(1L).get("state"));entry.setEnabled(false);assertEquals("DISABLED",service.stationStatus(1L).get("state"));}
 @Test void previewFrameCannotCrossCameraOrSurviveConfigurationChange(){
  when(entryMapper.selectById(1L)).thenReturn(entry);
  var frame=new com.linsight.module.aivideo.controller.node.task.vo.EntryStationFrameReqVO();
  frame.setCameraId(99L);frame.setTimestamp(System.currentTimeMillis());
  assertThrows(ServiceException.class,()->service.reportStation(2L,1L,5,"READY",frame));
  frame.setCameraId(3L);frame.setTimestamp(System.currentTimeMillis()-20000);
  assertThrows(ServiceException.class,()->service.reportStation(2L,1L,5,"READY",frame));
  frame.setTimestamp(System.currentTimeMillis());frame.setFaces(List.of());
  service.reportStation(2L,1L,5,"READY",frame);
  assertNotNull(service.stationStatus(1L).get("frame"));
  entry.setVersion(6);assertNull(service.stationStatus(1L).get("frame"));
  entry.setVersion(5);entry.setEnabled(false);assertNull(service.stationStatus(1L).get("frame"));
 }
}
