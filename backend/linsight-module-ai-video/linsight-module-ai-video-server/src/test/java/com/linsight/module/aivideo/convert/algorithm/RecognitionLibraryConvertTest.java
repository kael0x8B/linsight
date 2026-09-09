package com.linsight.module.aivideo.convert.algorithm;

import com.linsight.framework.common.pojo.PageResult;
import com.linsight.module.aivideo.controller.admin.algorithm.vo.RecognitionLibraryEntryRespVO;
import com.linsight.module.aivideo.dal.dataobject.algorithm.RecognitionLibraryEntryDO;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class RecognitionLibraryConvertTest {

    @Test
    void convertEntriesShouldParseAttributesJson() {
        RecognitionLibraryEntryDO entry = new RecognitionLibraryEntryDO();
        entry.setId(1L);
        entry.setLibraryId(2L);
        entry.setName("张三");
        entry.setExternalCode("EMP-001");
        entry.setAttributes("{\"schemaVersion\":\"1.0\",\"department\":\"生产部\"}");
        entry.setFeatureStatus("READY");
        entry.setStatus(0);

        PageResult<RecognitionLibraryEntryRespVO> result = RecognitionLibraryConvert.convertEntries(
                new PageResult<>(List.of(entry), 1L));

        assertThat(result.getList()).hasSize(1);
        assertThat(result.getList().get(0).getName()).isEqualTo("张三");
        assertThat(result.getList().get(0).getAttributes())
                .containsEntry("schemaVersion", "1.0")
                .containsEntry("department", "生产部");
    }
}
