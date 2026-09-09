package com.linsight.module.aivideo.dal.mysql.camera;

import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.linsight.module.aivideo.dal.dataobject.camera.CameraGroupDO;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface CameraGroupMapper extends BaseMapperX<CameraGroupDO> {

    default CameraGroupDO selectByParentIdAndName(Long parentId, String name) {
        return selectOne(CameraGroupDO::getParentId, parentId, CameraGroupDO::getName, name);
    }

    default long selectCountByParentId(Long parentId) {
        return selectCount(CameraGroupDO::getParentId, parentId);
    }

    default List<CameraGroupDO> selectList(String name, Integer status) {
        return selectList(new LambdaQueryWrapperX<CameraGroupDO>()
                .likeIfPresent(CameraGroupDO::getName, name)
                .eqIfPresent(CameraGroupDO::getStatus, status)
                .orderByAsc(CameraGroupDO::getParentId, CameraGroupDO::getSort, CameraGroupDO::getId));
    }

    default List<CameraGroupDO> selectDescendants(String pathPrefix) {
        return selectList(new LambdaQueryWrapperX<CameraGroupDO>()
                .likeRight(CameraGroupDO::getPath, pathPrefix)
                .orderByAsc(CameraGroupDO::getPath));
    }

    @Select("SELECT COUNT(*) FROM ai_camera WHERE group_id = #{groupId} AND deleted = b'0'")
    long selectCameraCountByGroupId(Long groupId);

}
