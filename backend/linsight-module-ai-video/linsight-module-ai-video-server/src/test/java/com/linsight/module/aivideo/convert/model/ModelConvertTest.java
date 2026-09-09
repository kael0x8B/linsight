package com.linsight.module.aivideo.convert.model;

import com.linsight.framework.common.pojo.PageResult;
import com.linsight.module.aivideo.dal.dataobject.model.ModelDO;
import com.linsight.module.aivideo.dal.dataobject.model.ModelVersionDO;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ModelConvertTest {
    @Test
    void catalogUsesDefaultVersionLabelsRatherThanNewerDraftOrAlgorithmAdoption() {
        ModelDO model = new ModelDO();
        model.setId(7L);
        model.setCurrentVersionId(10L);
        ModelVersionDO published = version(10L, "{\"decoder\":{\"labels\":[\"helmet\",\"no_helmet\"]}}");
        ModelVersionDO draft = version(11L, "{\"decoder\":{\"labels\":[\"person\"]}}");

        var result = ModelConvert.convertPage(new PageResult<>(List.of(model), 1L),
                List.of(draft, published), List.of()).getList().get(0);

        assertEquals(10L, result.getLatestVersionId());
        assertEquals(List.of("helmet", "no_helmet"), result.getOutputLabels());
        assertEquals(2, result.getVersionCount());
    }

    @Test
    void legacyManifestAndEmptyModelDoNotBreakCatalogOrInventLabels() {
        ModelDO model = new ModelDO();
        model.setId(7L);
        for (String manifest : List.of("", "not json", "{}", "{\"decoder\":{\"labels\":null}}")) {
            var result = ModelConvert.convertPage(new PageResult<>(List.of(model), 1L),
                    List.of(version(10L, manifest)), List.of()).getList().get(0);
            assertEquals(List.of(), result.getOutputLabels());
            assertEquals(1, result.getVersionCount());
        }
        var result = ModelConvert.convertPage(new PageResult<>(List.of(model), 1L),
                List.of(), List.of()).getList().get(0);
        assertEquals(0, result.getVersionCount());
        assertEquals(List.of(), result.getOutputLabels());
    }

    private static ModelVersionDO version(long id, String manifest) {
        ModelVersionDO version = new ModelVersionDO();
        version.setId(id);
        version.setModelId(7L);
        version.setRuntimeManifest(manifest);
        return version;
    }
}
