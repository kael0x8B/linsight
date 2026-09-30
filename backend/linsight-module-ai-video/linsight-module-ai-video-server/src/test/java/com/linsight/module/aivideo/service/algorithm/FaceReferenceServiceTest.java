package com.linsight.module.aivideo.service.algorithm;

import com.linsight.module.aivideo.dal.dataobject.algorithm.RecognitionLibraryDO;
import com.linsight.module.aivideo.dal.mysql.algorithm.*;
import com.linsight.module.infra.api.file.FileApi;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.*;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.transaction.support.TransactionTemplate;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.time.LocalDateTime;
import java.util.UUID;
import javax.imageio.ImageIO;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class FaceReferenceServiceTest {
    @Mock FaceReferenceMapper mapper;
    @Mock RecognitionLibraryMapper libraryMapper;
    @Mock RecognitionLibraryEntryMapper entryMapper;
    @Mock FileApi fileApi;
    @Mock TransactionTemplate transactionTemplate;
    @InjectMocks FaceReferenceService service;

    @Test void independentEnrollmentsCannotOverwriteEarlierReference() throws Exception {
        var library = new RecognitionLibraryDO();
        library.setLibraryType("FACE"); library.setStatus(0);
        when(libraryMapper.selectById(1L)).thenReturn(library);
        when(mapper.selectCount(any())).thenReturn(0L);
        when(transactionTemplate.execute(any())).thenReturn(1L);
        var bytes = new ByteArrayOutputStream();
        ImageIO.write(new BufferedImage(100,100,BufferedImage.TYPE_INT_RGB),"png",bytes);
        var first = UUID.randomUUID().toString(); var second = UUID.randomUUID().toString();
        service.register(1L,131L,"Synthetic A","A",LocalDateTime.now().plusDays(1),bytes.toByteArray(),first);
        service.register(1L,131L,"Synthetic B","B",LocalDateTime.now().plusDays(1),bytes.toByteArray(),second);
        var names = ArgumentCaptor.forClass(String.class);
        verify(fileApi,times(2)).createFile(any(),names.capture(),eq("ai-video/face-reference"),eq("image/png"));
        assertNotEquals(names.getAllValues().get(0),names.getAllValues().get(1));
        assertTrue(names.getAllValues().get(0).contains(first));
        assertTrue(names.getAllValues().get(1).contains(second));
    }

    private com.linsight.module.aivideo.dal.dataobject.algorithm.RecognitionLibraryEntryDO existing() {
        var e=new com.linsight.module.aivideo.dal.dataobject.algorithm.RecognitionLibraryEntryDO();
        e.setId(8L);e.setLibraryId(1L);e.setStatus(0);e.setMediaRef("stored-photo");
        e.setAttributes("{\"department\":\"demo\"}");
        var lib=new RecognitionLibraryDO();lib.setLibraryType("FACE");lib.setStatus(0);
        when(libraryMapper.selectById(1L)).thenReturn(lib);return e;
    }
    @Test void extractingExistingPersonKeepsItsIdentityAndUsesOriginalObject() {
        var e=existing();when(entryMapper.selectOne(any())).thenReturn(e);
        when(mapper.selectCount(any())).thenReturn(0L);
        String command=UUID.randomUUID().toString();
        service.registerExisting(new FaceReferenceService.ExistingPhoto(8L,"stored-photo","hash"),131L,LocalDateTime.now().plusDays(1),command);
        verify(entryMapper,never()).insert(any(com.linsight.module.aivideo.dal.dataobject.algorithm.RecognitionLibraryEntryDO.class));
        verify(mapper).insert(argThat((com.linsight.module.aivideo.dal.dataobject.algorithm.FaceReferenceDO r)->r.getEntryId()==8L&&r.getObjectRef().equals("stored-photo")));
        assertEquals("PENDING",e.getFeatureStatus());assertTrue(e.getAttributes().contains("PROCESSING"));
        assertTrue(e.getAttributes().contains("demo"));verifyNoInteractions(fileApi);
    }
    @Test void concurrentRequestCannotCreateSecondPendingReference() {
        var e=existing();when(entryMapper.selectOne(any())).thenReturn(e);
        var previous=new com.linsight.module.aivideo.dal.dataobject.algorithm.FaceReferenceDO();
        previous.setValidationStatus("PENDING");previous.setCreateTime(LocalDateTime.now());
        when(mapper.selectList(any())).thenReturn(java.util.List.of(previous));
        assertThrows(com.linsight.framework.common.exception.ServiceException.class,()->service.registerExisting(
          new FaceReferenceService.ExistingPhoto(8L,"stored-photo","hash"),131L,LocalDateTime.now().plusDays(1),UUID.randomUUID().toString()));
        verify(mapper,never()).insert(any(com.linsight.module.aivideo.dal.dataobject.algorithm.FaceReferenceDO.class));
    }
    @Test void reExtractionAppendsReferenceAndPreservesPreviousIdentityForAudit() {
        var e=existing();when(entryMapper.selectOne(any())).thenReturn(e);
        var previous=new com.linsight.module.aivideo.dal.dataobject.algorithm.FaceReferenceDO();
        previous.setId(12L);previous.setEntryId(8L);previous.setModelVersionId(130L);
        previous.setObjectRef("old-photo");previous.setValidationCommandId("old-command");previous.setValidationStatus("READY");
        when(mapper.selectList(any())).thenReturn(java.util.List.of(previous));
        when(mapper.selectCount(any())).thenReturn(0L);
        service.registerExisting(new FaceReferenceService.ExistingPhoto(8L,"stored-photo","hash"),131L,
                LocalDateTime.now().plusDays(1),"new-command");
        assertEquals(12L,previous.getId());assertEquals(130L,previous.getModelVersionId());
        assertEquals("old-photo",previous.getObjectRef());assertEquals("old-command",previous.getValidationCommandId());
        assertEquals("REVOKED",previous.getValidationStatus());
        verify(mapper).insert(argThat((com.linsight.module.aivideo.dal.dataobject.algorithm.FaceReferenceDO r)->
                r.getId()==null && r.getEntryId()==8L && r.getModelVersionId()==131L
                        && "new-command".equals(r.getValidationCommandId()) && "PENDING".equals(r.getValidationStatus())));
    }
    @Test void photoChangedWhilePreparingRejectsOldBytes() {
        var e=existing();e.setMediaRef("new-photo");when(entryMapper.selectOne(any())).thenReturn(e);
        assertThrows(com.linsight.framework.common.exception.ServiceException.class,()->service.registerExisting(
          new FaceReferenceService.ExistingPhoto(8L,"stored-photo","hash"),131L,LocalDateTime.now().plusDays(1),UUID.randomUUID().toString()));
        verifyNoInteractions(mapper);
    }
    @Test void failedValidationPersistsReadableReasonWithoutPrivatePayload() {
        var e=new com.linsight.module.aivideo.dal.dataobject.algorithm.RecognitionLibraryEntryDO();e.setId(8L);e.setAttributes("{}");
        var r=new com.linsight.module.aivideo.dal.dataobject.algorithm.FaceReferenceDO();
        r.setId(1L);r.setEntryId(8L);r.setValidationStatus("PENDING");r.setValidationCommandId("cmd");r.setModelVersionId(131L);r.setValidUntil(LocalDateTime.now().plusDays(1));
        when(mapper.selectById(1L)).thenReturn(r);when(entryMapper.selectOne(any())).thenReturn(e);
        service.applyValidation(1L,"cmd",false,java.util.Map.of("reason","NO_FACE","device","RKNPU","feature","secret","backend","https://secret"));
        assertEquals("FAILED",e.getFeatureStatus());assertTrue(e.getAttributes().contains("NO_FACE"));assertFalse(e.getAttributes().contains("secret"));
    }
    @Test void lateReportCannotReactivateSupersededReference() {
        var r=new com.linsight.module.aivideo.dal.dataobject.algorithm.FaceReferenceDO();r.setValidationCommandId("old");r.setValidationStatus("REVOKED");
        when(mapper.selectById(1L)).thenReturn(r);
        service.applyValidation(1L,"old",true);verifyNoInteractions(entryMapper);verify(mapper,never()).updateById(any(com.linsight.module.aivideo.dal.dataobject.algorithm.FaceReferenceDO.class));
    }
}
