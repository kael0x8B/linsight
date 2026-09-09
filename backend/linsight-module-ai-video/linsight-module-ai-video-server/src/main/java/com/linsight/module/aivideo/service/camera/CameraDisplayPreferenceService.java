package com.linsight.module.aivideo.service.camera;
import com.fasterxml.jackson.core.type.TypeReference;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.module.aivideo.dal.dataobject.camera.CameraDisplayPreferenceDO;
import com.linsight.module.aivideo.dal.mysql.camera.CameraDisplayPreferenceMapper;
import jakarta.annotation.Resource;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import java.util.List;
@Service
public class CameraDisplayPreferenceService {
 @Resource private CameraDisplayPreferenceMapper mapper;
 @Resource private CameraService cameraService;
 public List<String> get(Long userId, Long cameraId) {
  if(cameraService.getCamera(cameraId)==null) throw com.linsight.framework.common.exception.util.ServiceExceptionUtil.exception(com.linsight.module.aivideo.enums.camera.ErrorCodeConstants.CAMERA_NOT_FOUND);
  var row=mapper.find(userId,cameraId);
  if(row==null) return List.of();
  var values=JsonUtils.parseObjectQuietly(row.getHiddenLayersJson(),new TypeReference<List<String>>(){});
  return values==null ? List.of() : values;
 }
 public void save(Long userId, Long cameraId, List<String> hidden) {
  if(cameraService.getCamera(cameraId)==null) throw com.linsight.framework.common.exception.util.ServiceExceptionUtil.exception(com.linsight.module.aivideo.enums.camera.ErrorCodeConstants.CAMERA_NOT_FOUND);
  var row=mapper.find(userId,cameraId);
  if(row==null) {
   row=new CameraDisplayPreferenceDO(); row.setCameraId(cameraId);row.setUserId(userId);row.setHiddenLayersJson(JsonUtils.toJsonString(hidden.stream().distinct().toList()));
   try { mapper.insert(row); return; } catch(DuplicateKeyException race) { row=mapper.find(userId,cameraId); }
  }
  row.setHiddenLayersJson(JsonUtils.toJsonString(hidden.stream().distinct().toList()));mapper.updateById(row);
 }
}
