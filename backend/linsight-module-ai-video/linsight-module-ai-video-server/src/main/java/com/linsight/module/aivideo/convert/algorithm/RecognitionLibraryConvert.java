package com.linsight.module.aivideo.convert.algorithm;

import com.linsight.framework.common.pojo.PageResult;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.framework.common.util.object.BeanUtils;
import com.linsight.module.aivideo.controller.admin.algorithm.vo.RecognitionLibraryEntryRespVO;
import com.linsight.module.aivideo.controller.admin.algorithm.vo.RecognitionLibraryRespVO;
import com.linsight.module.aivideo.dal.dataobject.algorithm.RecognitionLibraryDO;
import com.linsight.module.aivideo.dal.dataobject.algorithm.RecognitionLibraryEntryDO;

import java.util.List;
import java.util.Map;

public final class RecognitionLibraryConvert {
    private RecognitionLibraryConvert() {
    }

    public static PageResult<RecognitionLibraryRespVO> convertLibraries(
            PageResult<RecognitionLibraryDO> page, Map<Long, Long> entryCounts) {
        List<RecognitionLibraryRespVO> list = page.getList().stream().map(item -> {
            RecognitionLibraryRespVO result = BeanUtils.toBean(item, RecognitionLibraryRespVO.class);
            result.setEntryCount(entryCounts.getOrDefault(item.getId(), 0L));
            return result;
        }).toList();
        return new PageResult<>(list, page.getTotal());
    }

    public static RecognitionLibraryRespVO convertLibrary(RecognitionLibraryDO item, long entryCount) {
        RecognitionLibraryRespVO result = BeanUtils.toBean(item, RecognitionLibraryRespVO.class);
        result.setEntryCount(entryCount);
        return result;
    }

    public static PageResult<RecognitionLibraryEntryRespVO> convertEntries(
            PageResult<RecognitionLibraryEntryDO> page) {
        List<RecognitionLibraryEntryRespVO> list = page.getList().stream().map(item -> {
            // attributes 在持久层是 JSON 字符串，在接口层是 Map，不能交给通用 Bean 转换器直接转换。
            RecognitionLibraryEntryRespVO result = new RecognitionLibraryEntryRespVO();
            result.setId(item.getId());
            result.setLibraryId(item.getLibraryId());
            result.setName(item.getName());
            result.setExternalCode(item.getExternalCode());
            result.setMediaRef(item.getMediaRef());
            result.setFeatureStatus(item.getFeatureStatus());
            result.setAttributes(item.getAttributes() == null ? Map.of() : JsonUtils.parseMap(item.getAttributes()));
            result.setStatus(item.getStatus());
            result.setCreateTime(item.getCreateTime());
            result.setUpdateTime(item.getUpdateTime());
            return result;
        }).toList();
        return new PageResult<>(list, page.getTotal());
    }
}
