import asyncio
import hashlib
import time
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest
from pydantic import ValidationError
from PIL import Image

from ai_runtime.app.model.face_pair import FaceQualityError
from ai_runtime.app.task.entry_access import EntryAccessRuntime, EntryRequest
from test_face_verification import FakeTasks


def request(tmp_path, **changes):
    path = tmp_path / 'reference.jpg'
    Image.new('RGB', (200, 200), 'white').save(path)
    values = dict(schemaVersion='1.0', sessionId=str(uuid4()), mode='IDENTIFY', consentConfirmed=True,
                  cameraId=2, modelVersionId=130, sourceUrl='rtsp://example/a',
                  expiresAtMillis=int(time.time()*1000)+3000,
                  references=[dict(entryId=10,path=path,sha256=hashlib.sha256(path.read_bytes()).hexdigest())],
                  roi=dict(x=0,y=0,width=1,height=1),similarityThreshold=.6,ambiguityMargin=.08,temporalN=2,temporalM=3)
    values.update(changes)
    return EntryRequest.model_validate(values)


class Pool:
    def __init__(self, values):
        self.values=iter(values)
        self.calls=0
    async def extract_face(self, version, image):
        self.calls+=1
        value=next(self.values,np.array([1.,0.]))
        if isinstance(value,Exception):raise value
        return np.asarray(value),SimpleNamespace(box=np.array([10,10,150,150])), 'RKNN_FACE_PAIR_SFACE','RKNPU'


@pytest.mark.parametrize('change',[dict(consentConfirmed=False),dict(consentConfirmed=1),dict(temporalN=5,temporalM=3),
                                  dict(roi=dict(x=.9,y=0,width=.2,height=1)),dict(cameraId=0)])
def test_contract(tmp_path,change):
    with pytest.raises(ValidationError):request(tmp_path,**change)


def test_enrollment_validates_without_camera_and_caches_no_names(tmp_path):
    async def run():
        tasks=FakeTasks();pool=Pool([[1,0]])
        service=EntryAccessRuntime(tasks,pool,tmp_path)
        result=await service.run(request(tmp_path,mode='ENROLL'))
        assert result['status']=='REFERENCE_READY' and tasks.active==0 and pool.calls==1
        assert result['device']=='RKNPU' and 'feature' not in result
    asyncio.run(run())


def test_invalid_reference_never_acquires_video(tmp_path):
    async def run():
        tasks=FakeTasks();service=EntryAccessRuntime(tasks,Pool([FaceQualityError('NO_FACE')]),tmp_path)
        result=await service.run(request(tmp_path,mode='ENROLL'))
        assert result['status']=='REFERENCE_INVALID' and result['reason']=='NO_FACE' and tasks.active==0
    asyncio.run(run())


@pytest.mark.parametrize('candidate,expected',[([1,0],'MATCH'),([0,1],'IDENTITY_UNCONFIRMED')])
def test_multiframe_classification_and_real_evidence_encoding(tmp_path,candidate,expected):
    async def run():
        tasks=FakeTasks();service=EntryAccessRuntime(tasks,Pool([[1,0]]+[candidate]*3),tmp_path)
        req=request(tmp_path)
        result=await service.run(req)
        assert result['status']==expected and result['matchedFrames']==3
        assert result['sampledFrames']==3 and result['liveness']=='NOT_VERIFIED' and tasks.active==0
        from pathlib import Path
        assert Path(result['snapshotPath']).exists() and Path(result['videoPath']).stat().st_size>0
        with pytest.raises(ValueError,match='already used'):await service.run(req)
    asyncio.run(run())


def test_no_match_on_invalid_last_frame(tmp_path):
    async def run():
        tasks=FakeTasks();pool=Pool([[1,0],[1,0],[1,0],FaceQualityError('MULTIPLE_FACES')]+[FaceQualityError('NO_FACE')]*20)
        service=EntryAccessRuntime(tasks,pool,tmp_path)
        result=await service.run(request(tmp_path,expiresAtMillis=int(time.time()*1000)+1300))
        assert result['status']=='EXPIRED' and result['matchedFrames']==0 and tasks.active==0
    asyncio.run(run())


def test_cancellation_releases_single_decoder_owner(tmp_path):
    async def run():
        tasks=FakeTasks();service=EntryAccessRuntime(tasks,Pool([[1,0]]),tmp_path);req=request(tmp_path)
        job=asyncio.create_task(service.run(req));await asyncio.sleep(.05);service.cancel(req.session_id)
        result=await job;assert result['status']=='CANCELLED' and tasks.active==0 and not service._active
    asyncio.run(run())


def test_reference_hash_and_expiry_fail_before_camera(tmp_path):
    async def run():
        tasks=FakeTasks();service=EntryAccessRuntime(tasks,Pool([]),tmp_path);req=request(tmp_path)
        req.references[0].sha256='0'*64
        with pytest.raises(ValueError,match='SHA256'):await service.run(req)
        with pytest.raises(ValueError,match='expired'):await service.run(request(tmp_path,expiresAtMillis=1))
        assert tasks.active==0
    asyncio.run(run())


def test_ambiguous_candidates_do_not_become_unknown_person_alarm(tmp_path):
    async def run():
        req=request(tmp_path)
        second=req.references[0].model_copy(update={'entry_id':11})
        req.references.append(second)
        tasks=FakeTasks();service=EntryAccessRuntime(tasks,Pool([[1,0]]*20),tmp_path)
        result=await service.run(req)
        assert result['status']=='EXPIRED' and result['reason']=='AMBIGUOUS_MATCH' and result['entryId'] is None
    asyncio.run(run())
