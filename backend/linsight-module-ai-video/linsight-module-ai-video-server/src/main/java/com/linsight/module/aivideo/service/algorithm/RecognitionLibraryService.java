package com.linsight.module.aivideo.service.algorithm;

import com.linsight.framework.common.pojo.PageResult;
import com.linsight.module.aivideo.controller.admin.algorithm.vo.RecognitionLibraryEntryPageReqVO;
import com.linsight.module.aivideo.controller.admin.algorithm.vo.RecognitionLibraryEntrySaveReqVO;
import com.linsight.module.aivideo.controller.admin.algorithm.vo.RecognitionLibraryPageReqVO;
import com.linsight.module.aivideo.controller.admin.algorithm.vo.RecognitionLibrarySaveReqVO;
import com.linsight.module.aivideo.dal.dataobject.algorithm.RecognitionLibraryDO;
import com.linsight.module.aivideo.dal.dataobject.algorithm.RecognitionLibraryEntryDO;

import java.util.Map;

public interface RecognitionLibraryService {
    PageResult<RecognitionLibraryDO> getLibraryPage(RecognitionLibraryPageReqVO reqVO);
    RecognitionLibraryDO getLibrary(Long id);
    Map<Long, Long> getEntryCounts(Iterable<RecognitionLibraryDO> libraries);
    long getEntryCount(Long libraryId);
    Long createLibrary(RecognitionLibrarySaveReqVO reqVO);
    void updateLibrary(RecognitionLibrarySaveReqVO reqVO);
    void deleteLibrary(Long id);
    PageResult<RecognitionLibraryEntryDO> getEntryPage(RecognitionLibraryEntryPageReqVO reqVO);
    Long createEntry(RecognitionLibraryEntrySaveReqVO reqVO);
    void updateEntry(RecognitionLibraryEntrySaveReqVO reqVO);
    void deleteEntry(Long id);
}
