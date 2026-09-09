package com.linsight.module.aivideo.service.algorithm;

import com.linsight.framework.common.pojo.PageResult;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.framework.common.util.object.BeanUtils;
import com.linsight.module.aivideo.controller.admin.algorithm.vo.RecognitionLibraryEntryPageReqVO;
import com.linsight.module.aivideo.controller.admin.algorithm.vo.RecognitionLibraryEntrySaveReqVO;
import com.linsight.module.aivideo.controller.admin.algorithm.vo.RecognitionLibraryPageReqVO;
import com.linsight.module.aivideo.controller.admin.algorithm.vo.RecognitionLibrarySaveReqVO;
import com.linsight.module.aivideo.dal.dataobject.algorithm.RecognitionLibraryDO;
import com.linsight.module.aivideo.dal.dataobject.algorithm.RecognitionLibraryEntryDO;
import com.linsight.module.aivideo.dal.mysql.algorithm.RecognitionLibraryEntryMapper;
import com.linsight.module.aivideo.dal.mysql.algorithm.RecognitionLibraryMapper;
import com.linsight.module.aivideo.service.model.ModelService;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.LinkedHashMap;
import java.util.Map;

import static com.linsight.framework.common.exception.util.ServiceExceptionUtil.exception;
import static com.linsight.module.aivideo.enums.algorithm.ErrorCodeConstants.*;

@Service
public class RecognitionLibraryServiceImpl implements RecognitionLibraryService {
    @Resource private RecognitionLibraryMapper libraryMapper;
    @Resource private RecognitionLibraryEntryMapper entryMapper;
    @Resource private ModelService modelService;
    @Resource private FaceReferenceService faceReferences;

    @Override
    public PageResult<RecognitionLibraryDO> getLibraryPage(RecognitionLibraryPageReqVO reqVO) {
        return libraryMapper.selectPage(reqVO, reqVO.getName(), reqVO.getLibraryType(), reqVO.getStatus());
    }

    @Override
    public RecognitionLibraryDO getLibrary(Long id) {
        return requireLibrary(id);
    }

    @Override
    public Map<Long, Long> getEntryCounts(Iterable<RecognitionLibraryDO> libraries) {
        Map<Long, Long> result = new LinkedHashMap<>();
        libraries.forEach(item -> result.put(item.getId(), entryMapper.selectCountByLibraryId(item.getId())));
        return result;
    }

    @Override
    public long getEntryCount(Long libraryId) {
        requireLibrary(libraryId);
        return entryMapper.selectCountByLibraryId(libraryId);
    }

    @Override
    public Long createLibrary(RecognitionLibrarySaveReqVO reqVO) {
        if (libraryMapper.selectByCode(reqVO.getCode()) != null) throw exception(RECOGNITION_LIBRARY_CODE_DUPLICATE);
        validateEngine(reqVO.getEngineModelVersionId());
        RecognitionLibraryDO library = BeanUtils.toBean(reqVO, RecognitionLibraryDO.class);
        libraryMapper.insert(library);
        return library.getId();
    }

    @Override
    public void updateLibrary(RecognitionLibrarySaveReqVO reqVO) {
        RecognitionLibraryDO existing = requireLibrary(reqVO.getId());
        if (!existing.getCode().equals(reqVO.getCode()) || !existing.getLibraryType().equals(reqVO.getLibraryType())) {
            throw exception(RECOGNITION_LIBRARY_IDENTITY_IMMUTABLE);
        }
        validateEngine(reqVO.getEngineModelVersionId());
        libraryMapper.updateById(BeanUtils.toBean(reqVO, RecognitionLibraryDO.class));
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void deleteLibrary(Long id) {
        requireLibrary(id);
        if (entryMapper.selectCountByLibraryId(id) > 0) throw exception(RECOGNITION_LIBRARY_NOT_EMPTY);
        libraryMapper.deleteById(id);
    }

    @Override
    public PageResult<RecognitionLibraryEntryDO> getEntryPage(RecognitionLibraryEntryPageReqVO reqVO) {
        requireLibrary(reqVO.getLibraryId());
        return entryMapper.selectPage(reqVO, reqVO.getLibraryId(), reqVO.getName(),
                reqVO.getFeatureStatus(), reqVO.getStatus());
    }

    @Override
    public Long createEntry(RecognitionLibraryEntrySaveReqVO reqVO) {
        var library = requireLibrary(reqVO.getLibraryId());
        RecognitionLibraryEntryDO entry = toEntry(reqVO);
        if ("FACE".equals(library.getLibraryType())) {
            entry.setFeatureStatus("PENDING");
            var attrs = new LinkedHashMap<>(reqVO.getAttributes() == null ? Map.<String,Object>of() : reqVO.getAttributes());
            attrs.remove("faceExtraction");entry.setAttributes(JsonUtils.toJsonString(attrs));
        }
        entryMapper.insert(entry);
        return entry.getId();
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void updateEntry(RecognitionLibraryEntrySaveReqVO reqVO) {
        RecognitionLibraryEntryDO existing = entryMapper.selectOne(new com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX<RecognitionLibraryEntryDO>()
                .eq(RecognitionLibraryEntryDO::getId,reqVO.getId()).last("FOR UPDATE"));
        if(existing == null) throw exception(RECOGNITION_LIBRARY_ENTRY_NOT_FOUND);
        if (!existing.getLibraryId().equals(reqVO.getLibraryId())) throw exception(RECOGNITION_LIBRARY_IDENTITY_IMMUTABLE);
        var update = toEntry(reqVO);
        if ("FACE".equals(requireLibrary(existing.getLibraryId()).getLibraryType())) {
            var attrs = new LinkedHashMap<>(reqVO.getAttributes() == null ? Map.<String,Object>of() : reqVO.getAttributes());
            attrs.remove("faceExtraction");
            boolean changed = !java.util.Objects.equals(existing.getMediaRef(),reqVO.getMediaRef());
            var oldAttrs = existing.getAttributes() == null ? Map.<String,Object>of() : JsonUtils.parseMap(existing.getAttributes());
            if (changed) faceReferences.invalidateEntry(existing.getId());
            else if (oldAttrs.containsKey("faceExtraction")) attrs.put("faceExtraction",oldAttrs.get("faceExtraction"));
            update.setFeatureStatus(changed ? "PENDING" : existing.getFeatureStatus());
            update.setAttributes(JsonUtils.toJsonString(attrs));
        }
        entryMapper.updateById(update);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void deleteEntry(Long id) {
        var entry=requireEntry(id);
        if ("FACE".equals(requireLibrary(entry.getLibraryId()).getLibraryType())) faceReferences.invalidateEntry(id);
        entryMapper.deleteById(id);
    }

    private void validateEngine(Long modelVersionId) {
        if (modelVersionId == null) return;
        var version = modelService.getVersion(modelVersionId);
        if (!"PUBLISHED".equals(version.getPublishStatus()) || !"READY".equals(version.getExecutionStatus())) {
            throw exception(RECOGNITION_LIBRARY_ENGINE_NOT_READY);
        }
    }

    private RecognitionLibraryDO requireLibrary(Long id) {
        RecognitionLibraryDO result = id == null ? null : libraryMapper.selectById(id);
        if (result == null) throw exception(RECOGNITION_LIBRARY_NOT_FOUND);
        return result;
    }

    private RecognitionLibraryEntryDO requireEntry(Long id) {
        RecognitionLibraryEntryDO result = id == null ? null : entryMapper.selectById(id);
        if (result == null) throw exception(RECOGNITION_LIBRARY_ENTRY_NOT_FOUND);
        return result;
    }

    private static RecognitionLibraryEntryDO toEntry(RecognitionLibraryEntrySaveReqVO reqVO) {
        RecognitionLibraryEntryDO entry = new RecognitionLibraryEntryDO();
        entry.setId(reqVO.getId());
        entry.setLibraryId(reqVO.getLibraryId());
        entry.setName(reqVO.getName());
        entry.setExternalCode(reqVO.getExternalCode());
        entry.setMediaRef(reqVO.getMediaRef());
        entry.setFeatureStatus(reqVO.getFeatureStatus());
        entry.setAttributes(JsonUtils.toJsonString(reqVO.getAttributes()));
        entry.setStatus(reqVO.getStatus());
        return entry;
    }
}
