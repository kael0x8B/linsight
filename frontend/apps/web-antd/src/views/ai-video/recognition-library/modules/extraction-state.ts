import type { AiVideoRecognitionLibraryApi } from '#/api/ai-video/recognition-library';
const reasons: Record<string,string> = {
  NO_FACE:'未检测到人脸，请上传清晰的单人正面照片。',
  MULTIPLE_FACES:'照片中有多个人脸，请使用单人照片。',
  FACE_TOO_SMALL:'人脸太小，请使用更近、更清晰的正面照片。',
  FACE_CLIPPED:'人脸未完整进入照片，请更换完整的正面照片。',
  INSUFFICIENT_IMAGE_QUALITY:'照片清晰度或光照不足，请重新拍摄。',
  INVALID_LANDMARKS:'五官定位失败，请上传无遮挡的正面照片。',
  EXECUTION_FAILED:'网关执行失败，请检查节点和模型状态后重试。',
  CANCELLED:'本次提取已取消，可以重新提取。',
};
export function extractionState(entry: Pick<AiVideoRecognitionLibraryApi.Entry,'featureStatus'|'attributes'|'mediaRef'>, now=Date.now()) {
  const m=(entry.attributes?.faceExtraction ?? {}) as Record<string,unknown>;
  if(m.status==='PROCESSING') {
    const processing=now-Number(m.requestedAt)<180000;
    return {label:processing?'提取中':'提取超时',color:processing?'processing':'warning',processing,action:processing?'正在提取':'重试提取',hint:processing?'边缘网关正在校验照片，完成后自动更新。':'未收到网关结果，请检查节点连接后重试。'};
  }
  if(entry.featureStatus==='READY'&&m.status==='READY') {
    const expired=Date.parse(String(m.validUntil))<=now;
    return {label:expired?'已过期':'已就绪',color:expired?'warning':'success',processing:false,action:expired?'重新提取':'更新特征',hint:expired?'参考有效期已结束，请重新设置有效期并提取。':`${m.device==='RKNPU'?'NPU 校验通过。':'网关校验通过。'}可在摄像头中选择此人员。`};
  }
  if(entry.featureStatus==='FAILED') return {label:'提取失败',color:'error',processing:false,action:'重试提取',hint:reasons[String(m.reason)]??'照片未通过校验，请使用清晰的单人正面照片重试。'};
  return {label:'待提取',color:'default',processing:false,action:'提取特征',hint:entry.mediaRef?'照片已保存，点击“提取特征”完成网关校验。':'请先编辑人员并上传正面照片。'};
}
