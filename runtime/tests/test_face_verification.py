import asyncio
import io
import time
from contextlib import asynccontextmanager
from uuid import uuid4

import numpy as np
import pytest
from PIL import Image
from pydantic import ValidationError

from ai_runtime.app.model.face_pair import ALIGNMENT_POINTS, FaceQualityError, align_face
from ai_runtime.app.stream.frames import CapturedFrame
from ai_runtime.app.task.face_verification import FaceVerificationRequest, FaceVerificationService


def request(tmp_path, **overrides):
    path = tmp_path / 'reference.jpg'
    Image.new('RGB', (200, 200), 'white').save(path)
    payload = dict(schemaVersion='1.0', sessionId=str(uuid4()), consentConfirmed=True,
                   cameraId=2, modelVersionId=130, referencePath=path, sourceUrl='rtsp://example/a',
                   expiresAtMillis=time.time_ns() // 1_000_000 + 3000,
                   roi=dict(x=0, y=0, width=1, height=1), similarityThreshold=.6,
                   temporalN=2, temporalM=3, validationOnly=True)
    payload.update(overrides)
    return FaceVerificationRequest.model_validate(payload)


class FakeTasks:
    active = 0
    @asynccontextmanager
    async def camera_samples(self, _camera, _url):
        self.active += 1
        queue = asyncio.Queue(maxsize=1)
        async def feed():
            while True:
                await asyncio.sleep(.3)
                data = io.BytesIO()
                Image.new('RGB', (200, 200), 'white').save(data, format='JPEG')
                if queue.full():
                    queue.get_nowait()
                queue.put_nowait(CapturedFrame(data.getvalue(), time.time_ns() // 1_000_000))
        feeder = asyncio.create_task(feed())
        try:
            yield queue
        finally:
            feeder.cancel()
            self.active -= 1


class FakePool:
    def __init__(self, scores):
        self.scores = iter(scores)
        self.calls = 0
    async def compare_faces(self, _model, _reference, _image):
        self.calls += 1
        if self.calls == 1:
            return {'similarity': 1.0}
        score = next(self.scores, 0)
        if isinstance(score, Exception):
            raise score
        return {'similarity': score}


def test_alignment_identity_and_translation():
    random = np.random.default_rng(7).integers(0, 256, (112, 112, 3), dtype=np.uint8)
    image = Image.fromarray(random)
    result = align_face(image, ALIGNMENT_POINTS)
    assert np.abs(np.asarray(result).astype(float) - random).mean() < 1
    large = Image.new('RGB', (140, 140))
    large.paste(image, (10, 12))
    shifted = align_face(large, ALIGNMENT_POINTS + [10, 12])
    assert np.abs(np.asarray(shifted).astype(float) - random).mean() < 1


@pytest.mark.parametrize('points', [np.zeros((5, 2)), np.full((5, 2), np.nan), np.zeros((4, 2))])
def test_bad_landmarks_rejected(points):
    with pytest.raises(FaceQualityError):
        align_face(Image.new('RGB', (112, 112)), points)


@pytest.mark.parametrize('overrides', [dict(consentConfirmed=False), dict(validationOnly=False),
    dict(temporalN=5, temporalM=3), dict(roi=dict(x=.9,y=0,width=.2,height=1))])
def test_explicit_development_session_contract(tmp_path, overrides):
    with pytest.raises(ValidationError):
        request(tmp_path, **overrides)


def test_multiframe_match_and_release_and_replay_rejected(tmp_path):
    async def check():
        tasks = FakeTasks()
        pool = FakePool([.8, .2, .9])
        service = FaceVerificationService(tasks, pool)
        req = request(tmp_path)
        result = await service.verify(req)
        assert result.status == 'MATCH' and result.sampled_frames == 3
        assert result.matched_frames == 2 and result.liveness == 'NOT_VERIFIED'
        assert tasks.active == 0
        with pytest.raises(ValueError, match='already used'):
            await service.verify(req)
    asyncio.run(check())


def test_quality_failure_is_not_identity_or_permission_denial(tmp_path):
    async def check():
        tasks = FakeTasks()
        pool = FakePool([FaceQualityError('MULTIPLE_FACES')] * 12)
        result = await FaceVerificationService(tasks, pool).verify(request(tmp_path))
        assert result.status == 'NOT_CONFIRMED' and result.matched_frames == 0
        assert result.reason == 'MULTIPLE_FACES' and tasks.active == 0
    asyncio.run(check())


def test_expired_or_unbounded_session_never_acquires_camera(tmp_path):
    async def check():
        tasks = FakeTasks()
        pool = FakePool([])
        service = FaceVerificationService(tasks, pool)
        for expires in [1, time.time_ns() // 1_000_000 + 60000]:
            with pytest.raises(ValueError, match='expired or exceeds'):
                await service.verify(request(tmp_path, expiresAtMillis=expires))
        assert tasks.active == pool.calls == 0
    asyncio.run(check())


def test_cancel_releases_stream_and_reservation(tmp_path):
    async def check():
        tasks = FakeTasks()
        service = FaceVerificationService(tasks, FakePool([0] * 20))
        job = asyncio.create_task(service.verify(request(tmp_path)))
        await asyncio.sleep(.1)
        job.cancel()
        with pytest.raises(asyncio.CancelledError):
            await job
        assert tasks.active == 0 and not service._active_cameras
    asyncio.run(check())
