package com.linsight.module.aivideo.service.algorithm;

import com.linsight.framework.common.exception.ServiceException;
import com.linsight.module.aivideo.controller.admin.algorithm.vo.RecognitionLibrarySaveReqVO;
import com.linsight.module.aivideo.dal.dataobject.algorithm.RecognitionLibraryDO;
import com.linsight.module.aivideo.dal.dataobject.model.ModelVersionDO;
import com.linsight.module.aivideo.dal.mysql.algorithm.RecognitionLibraryEntryMapper;
import com.linsight.module.aivideo.dal.mysql.algorithm.RecognitionLibraryMapper;
import com.linsight.module.aivideo.service.model.ModelService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class RecognitionLibraryServiceImplTest {

    @Mock private RecognitionLibraryMapper libraryMapper;
    @Mock private RecognitionLibraryEntryMapper entryMapper;
    @Mock private ModelService modelService;
    @InjectMocks private RecognitionLibraryServiceImpl service;

    @Test
    void createLibraryAcceptsPublishedReadyRecognitionEngine() {
        RecognitionLibrarySaveReqVO request = request();
        ModelVersionDO version = new ModelVersionDO();
        version.setPublishStatus("PUBLISHED");
        version.setExecutionStatus("READY");
        when(modelService.getVersion(88L)).thenReturn(version);

        service.createLibrary(request);

        verify(libraryMapper).insert(any(RecognitionLibraryDO.class));
    }

    @Test
    void createLibraryRejectsEngineThatCannotExecute() {
        RecognitionLibrarySaveReqVO request = request();
        ModelVersionDO version = new ModelVersionDO();
        version.setPublishStatus("PUBLISHED");
        version.setExecutionStatus("NOT_READY");
        when(modelService.getVersion(88L)).thenReturn(version);

        ServiceException error = assertThrows(ServiceException.class,
                () -> service.createLibrary(request));

        assertEquals(1_020_002_025, error.getCode());
    }

    @Test
    void deleteLibraryRejectsNonEmptyLibrary() {
        RecognitionLibraryDO library = new RecognitionLibraryDO();
        library.setId(7L);
        when(libraryMapper.selectById(7L)).thenReturn(library);
        when(entryMapper.selectCountByLibraryId(7L)).thenReturn(2L);

        ServiceException error = assertThrows(ServiceException.class,
                () -> service.deleteLibrary(7L));

        assertEquals(1_020_002_023, error.getCode());
    }

    private static RecognitionLibrarySaveReqVO request() {
        RecognitionLibrarySaveReqVO request = new RecognitionLibrarySaveReqVO();
        request.setName("访客人脸库");
        request.setCode("visitor-face");
        request.setLibraryType("FACE");
        request.setEngineModelVersionId(88L);
        request.setFeatureDimension(512);
        request.setMatchMode("ONE_TO_N");
        request.setStatus(0);
        return request;
    }

    @Test void faceStatusCannotBeManuallyMarkedReady() {
        var library=new RecognitionLibraryDO();library.setId(7L);library.setLibraryType("FACE");
        when(libraryMapper.selectById(7L)).thenReturn(library);
        var request=new com.linsight.module.aivideo.controller.admin.algorithm.vo.RecognitionLibraryEntrySaveReqVO();
        request.setLibraryId(7L);request.setFeatureStatus("READY");request.setAttributes(java.util.Map.of("faceExtraction",java.util.Map.of("status","READY")));
        service.createEntry(request);
        verify(entryMapper).insert(org.mockito.ArgumentMatchers.argThat((com.linsight.module.aivideo.dal.dataobject.algorithm.RecognitionLibraryEntryDO e)->e.getFeatureStatus().equals("PENDING")&&!e.getAttributes().contains("faceExtraction")));
    }
}
