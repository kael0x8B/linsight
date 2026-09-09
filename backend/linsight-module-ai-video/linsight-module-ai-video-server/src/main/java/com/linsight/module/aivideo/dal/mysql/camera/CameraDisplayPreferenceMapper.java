package com.linsight.module.aivideo.dal.mysql.camera;
import com.linsight.framework.mybatis.core.mapper.BaseMapperX;
import com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.linsight.module.aivideo.dal.dataobject.camera.CameraDisplayPreferenceDO;
import org.apache.ibatis.annotations.Mapper;
@Mapper
public interface CameraDisplayPreferenceMapper extends BaseMapperX<CameraDisplayPreferenceDO> {
 default CameraDisplayPreferenceDO find(Long userId, Long cameraId) {
  return selectOne(new LambdaQueryWrapperX<CameraDisplayPreferenceDO>().eq(CameraDisplayPreferenceDO::getUserId,userId).eq(CameraDisplayPreferenceDO::getCameraId,cameraId));
 }
}
