import { describe, expect, it } from 'vitest';
import { extractionState } from './extraction-state';
const entry={featureStatus:'PENDING' as const,attributes:{},mediaRef:'photo'};
describe('person extraction state',()=>{
 it('does not treat manually marked READY as verified',()=>expect(extractionState({...entry,featureStatus:'READY'}).label).toBe('待提取'));
 it('offers retry for abandoned processing',()=>expect(extractionState({...entry,attributes:{faceExtraction:{status:'PROCESSING',requestedAt:100}}},180101)).toMatchObject({processing:false,action:'重试提取'}));
 it('shows processing for active command',()=>expect(extractionState({...entry,attributes:{faceExtraction:{status:'PROCESSING',requestedAt:100}}},200)).toMatchObject({processing:true,label:'提取中'}));
 it('explains failed photo quality',()=>expect(extractionState({...entry,featureStatus:'FAILED',attributes:{faceExtraction:{reason:'NO_FACE'}}}).hint).toContain('未检测到人脸'));
 it('only marks validated unexpired photo usable',()=>expect(extractionState({...entry,featureStatus:'READY',attributes:{faceExtraction:{status:'READY',validUntil:'2026-09-09T00:00:00',device:'RKNPU'}}},Date.parse('2026-09-08T00:00:00'))).toMatchObject({label:'已就绪',hint:'NPU 校验通过。可在摄像头中选择此人员。'}));
 it('expired reference needs renewal',()=>expect(extractionState({...entry,featureStatus:'READY',attributes:{faceExtraction:{status:'READY',validUntil:'2026-09-01'}}}).label).toBe('已过期'));
});
