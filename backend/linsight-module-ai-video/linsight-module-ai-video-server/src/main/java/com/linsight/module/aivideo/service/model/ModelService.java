package com.linsight.module.aivideo.service.model;

import com.linsight.framework.common.pojo.PageResult;
import com.linsight.module.aivideo.controller.admin.model.vo.ModelPageReqVO;
import com.linsight.module.aivideo.controller.admin.model.vo.ModelSaveReqVO;
import com.linsight.module.aivideo.controller.admin.model.vo.ModelVersionUploadReqVO;
import com.linsight.module.aivideo.dal.dataobject.model.ModelDO;
import com.linsight.module.aivideo.dal.dataobject.model.ModelVersionDO;

import java.io.IOException;
import java.util.List;
import java.util.Collection;

public interface ModelService {
    java.util.Map<Long, java.util.Map<String, String>> getVersionDisplayNames(Collection<Long> versionIds);
    Long createModel(ModelSaveReqVO reqVO);
    void updateModel(ModelSaveReqVO reqVO);
    void deleteModel(Long id);
    ModelDO getModel(Long id);
    ModelVersionDO getVersion(Long id);
    PageResult<ModelDO> getModelPage(ModelPageReqVO reqVO);
    Long uploadVersion(ModelVersionUploadReqVO reqVO) throws IOException;
    List<ModelVersionDO> getVersionList(Long modelId);
    List<ModelVersionDO> getVersionList(Collection<Long> modelIds);
    void publishVersion(Long versionId);
}
