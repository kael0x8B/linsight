"""Independent package policy and the backward-compatible observation boundary."""

import asyncio
import copy
import importlib.util
import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from ai_runtime.app.capability.package_runner import PackageRunner
from ai_runtime.app.capability.packages import (
    AlgorithmPackageStore,
    inspect_package,
    validate_bindings,
    validate_manifest,
)
from ai_runtime.app.capability.postprocess import CapabilityPostprocessor
from ai_runtime.app.capability.tracker import IoUTracker
from ai_runtime.app.model.contracts import DetectionObject, ModelTestResult
from ai_runtime.app.model.plate import PLATE_CHARACTERS, decode_chinese_plate_ctc
from ai_runtime.app.model.plate_evidence import body_agrees
from ai_runtime.app.task.contracts import TaskInferenceParameters
from ai_runtime.app.task.inference import TaskFrameInference

ROOT = Path(__file__).parents[1] / 'algorithm_packages/xinjiang-plate'
MANIFEST = json.loads((ROOT / 'algorithm.json').read_text())
SPEC = importlib.util.spec_from_file_location('xinjiang_test_package', ROOT / 'processor.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def package():
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for path in ROOT.iterdir():
            if path.suffix in {'.py', '.json', '.md'}:
                archive.writestr(path.name, path.read_bytes())
    return output.getvalue()


def plate(text='浙A12345', scores=None, track='one', body_score=.96):
    if scores is None:
        scores = {'浙': .44, '新': .4}
    has_province = text[0] in MODULE.PROVINCES
    chars = [{'char': c, 'score': scores[c] if i == 0 and has_province else body_score}
             for i, c in enumerate(text)]
    values = [c['score'] for c in chars]
    return {
        'class': 'license_plate', 'confidence': .92, 'trackId': track,
        'bbox': {'x': .3, 'y': .4, 'width': .3, 'height': .1},
        'attributes': {'plateText': text, 'ocrConfidence': sum(values) / len(values),
                       'ocrMinCharConfidence': min(values),
                       'ocrEvidenceJson': json.dumps({'schemaVersion': '1.0',
                           'characters': chars, 'provinceScores': scores})},
    }


def frame(objects, timestamp, **parameters):
    return {'objects': objects, 'timestampMillis': timestamp,
            'parameters': {**MANIFEST['defaultParameters'], **parameters},
            'runtimeCapabilities': ['plate-ocr-evidence-v1']}


def run_sequence(objects, **parameters):
    algorithm = MODULE.Algorithm()
    output = []
    for i, obj in enumerate(objects):
        output = algorithm.process(frame([] if obj is None else [obj], i * 250,
                                         **parameters), None)['objects']
    return output


def test_near_tie_uses_xin_only_after_three_frames_and_keeps_raw_scores():
    original = plate()
    assert run_sequence([original])[0]['attributes']['eventCandidate'] is False
    attrs = run_sequence([original] * 3)[0]['attributes']
    assert attrs['plateNumber'] == '新A12345'
    assert attrs['provinceSource'] == 'REGION_ASSISTED'
    assert attrs['ocrStatus'] == 'CONFIRMED'
    assert attrs['plateText'] == '浙A12345'
    assert attrs['ocrConfidence'] == original['attributes']['ocrConfidence']
    assert attrs['ocrMinCharConfidence'] == .44
    assert attrs['displayConfidence'] is None
    assert 'plateConfidence' not in attrs


def test_same_observations_leave_legacy_algorithm_pending():
    processor = CapabilityPostprocessor(
        {'nodes': [{'capabilityKey': 'ocr.license-plate'}]},
        TaskInferenceParameters(schemaVersion='1.0'),
    )
    for i in range(3):
        result = processor.after_tracking([DetectionObject.model_validate(plate())], i * 250)
        assert result[0].attributes['ocrStatus'] == 'LOW_CHAR_CONFIDENCE'
        assert processor.event_candidates(result) == []


@pytest.mark.parametrize('province', ['浙', '粤', '新', '京'])
def test_clear_province_is_preserved(province):
    obj = plate(province + 'A12345', {province: .96})
    attrs = run_sequence([obj] * 3)[0]['attributes']
    assert attrs['plateNumber'] == province + 'A12345'
    assert attrs['provinceSource'] == 'OCR'


def test_clear_external_evidence_vetoes_ambiguous_xin_votes():
    strong = plate('浙A12345', {'浙': .96, '新': .01})
    attrs = run_sequence([plate(), strong, plate(), plate()])[0]['attributes']
    assert 'plateNumber' not in attrs
    assert not attrs['eventCandidate']


@pytest.mark.parametrize('scores', [{'浙': .7, '新': .1}, {'浙': .15, '新': .14}])
def test_large_gap_or_no_visual_support_never_rewrites(scores):
    attrs = run_sequence([plate(scores=scores)] * 5)[0]['attributes']
    assert 'plateNumber' not in attrs


def test_weak_body_is_never_rescued_by_region_prior():
    attrs = run_sequence([plate(body_score=.45)] * 5)[0]['attributes']
    assert attrs['ocrStatus'] == 'LOW_BODY_CONFIDENCE'
    assert not attrs['eventCandidate']


def test_missing_province_is_opt_in_and_events_need_a_separate_opt_in():
    obj = plate('A12345', {})
    assert 'plateNumber' not in run_sequence([obj] * 5)[0]['attributes']
    attrs = run_sequence([obj] * 3, allowMissingProvince=True)[0]['attributes']
    assert attrs['plateNumber'] == '新A12345'
    assert attrs['provinceSource'] == 'REGION_INFERRED'
    assert attrs['ocrStatus'] == 'INFERRED'
    assert not attrs['eventCandidate']
    attrs = run_sequence([obj] * 3, allowMissingProvince=True,
                         allowInferredEvents=True)[0]['attributes']
    assert attrs['eventCandidate']
    assert attrs['provinceSource'] == 'REGION_INFERRED'


def test_duplicate_frame_missing_frames_and_split_tracks_do_not_manufacture_votes():
    algorithm = MODULE.Algorithm()
    for _ in range(5):
        attrs = algorithm.process(frame([plate()], 100), None)['objects'][0]['attributes']
        assert 'plateNumber' not in attrs
        assert attrs['ocrVoteFrames'] == 1
    attrs = run_sequence([plate(), None, plate(), None, None, plate()])[0]['attributes']
    assert 'plateNumber' not in attrs
    attrs = run_sequence([plate(track='a'), plate(track='b'), plate(track='a')])[0]['attributes']
    assert 'plateNumber' not in attrs


def test_conflicting_bodies_and_stale_votes_stay_pending():
    attrs = run_sequence([plate('浙A12345'), plate('浙A12346'), plate('浙A12345')])[0]['attributes']
    assert 'plateNumber' not in attrs
    algorithm = MODULE.Algorithm()
    for timestamp in [0, 250, 11000, 11250]:
        attrs = algorithm.process(frame([plate()], timestamp), None)['objects'][0]['attributes']
        assert 'plateNumber' not in attrs
    attrs = algorithm.process(frame([plate()], 1), None)['objects'][0]['attributes']
    assert attrs['ocrVoteFrames'] == 1


@pytest.mark.parametrize('text', ['浙AD12345', '浙A1234挂'])
def test_eight_character_and_trailer_bodies_are_preserved(text):
    assert run_sequence([plate(text)] * 3)[0]['attributes']['plateNumber'] == '新' + text[1:]


def test_evidence_must_match_text_and_have_valid_scores():
    for mutate in [lambda a: a.pop('ocrEvidenceJson'),
                   lambda a: a.update(plateText='浙A54321'),
                   lambda a: a.update(ocrEvidenceJson='{}')]:
        obj = plate()
        mutate(obj['attributes'])
        assert not run_sequence([obj] * 3)[0]['attributes']['eventCandidate']
    assert MODULE.observation(plate(body_score=float('nan'))['attributes'],
                              MANIFEST['defaultParameters']) is None


def test_ctc_evidence_is_opt_in_and_does_not_change_legacy_outputs():
    indices = [0]
    for char in '浙AA1122':
        indices.extend([PLATE_CHARACTERS.index(char)] * 2 + [0])
    logits = np.full((1, len(indices), len(PLATE_CHARACTERS)), -8.)
    for t, index in enumerate(indices):
        logits[0, t, index] = 8
    logits[0, 1, PLATE_CHARACTERS.index('新')] = 7.9
    colors = np.zeros((1, 5))
    legacy = decode_chinese_plate_ctc(logits, colors)[0].model_dump()
    enhanced = decode_chinese_plate_ctc(logits, colors, evidence=True)[0].model_dump()
    evidence = json.loads(enhanced['attributes'].pop('ocrEvidenceJson'))
    assert enhanced == legacy
    assert ''.join(c['char'] for c in evidence['characters']) == '浙AA1122'
    assert evidence['provinceScores']['新'] > .4
    assert len(evidence['characters']) == 7


def test_routed_site_evidence_preserves_separators_and_excludes_blank(monkeypatch):
    from test_plate_routed import SiteSession, _parameters

    from ai_runtime.app.model import plate_routed

    adapter = plate_routed.RoutedPlateOcrAdapter.__new__(plate_routed.RoutedPlateOcrAdapter)
    adapter._site = plate_routed.PaddlePlateTextRecognizer(SiteSession())
    monkeypatch.setattr(plate_routed, 'plate_number_region',
                        lambda source: (source.crop((20, 0, 180, 48)), 20))
    with Image.new('RGB', (180, 48)) as image:
        legacy = adapter.infer_image(image, _parameters()).objects[0].model_dump()
        parameters = _parameters().model_copy(update={'ocr_evidence': True})
        enhanced = adapter.infer_image(image, parameters).objects[0].model_dump()
    evidence = json.loads(enhanced['attributes'].pop('ocrEvidenceJson'))
    assert enhanced == legacy
    assert ''.join(c['char'] for c in evidence['characters']) == '吉WD0010'
    assert evidence['provinceScores'] == {'吉': 1}
    assert MODULE.observation(
        {**enhanced['attributes'], 'ocrEvidenceJson': json.dumps(evidence)},
        MANIFEST['defaultParameters'],
    )['body'] == 'WD0010'


def test_crop_agreement_accepts_only_matching_strong_bodies_without_clear_conflict():
    first, second = plate(), plate('新A12345', {'新': .44, '浙': .4})
    assert body_agrees(first['attributes'], second['attributes'], .75)
    assert not body_agrees(first['attributes'], plate('浙A12346')['attributes'], .75)
    assert not body_agrees(plate('浙A12345', {'浙': .95})['attributes'],
                           second['attributes'], .75)
    assert not body_agrees(first['attributes'], plate(body_score=.5)['attributes'], .75)


def test_manifest_requires_capability_and_models_that_supply_evidence():
    inspect_package(package())
    for mutate in [lambda m: m.update(runtimeRequirements=[]),
                   lambda m: m['frameInput'].update(ocrSlot='plate'),
                   lambda m: m['models'][1].update(decoderTypes=['LPRNET'])]:
        manifest = copy.deepcopy(MANIFEST)
        mutate(manifest)
        with pytest.raises(ValueError):
            validate_manifest(manifest)
    models = [
        {'modelVersionId': 1, 'artifactFormat': 'ONNX',
         'runtimeManifest': {'taskType': 'OBJECT_DETECTION', 'decoder': {'type': 'YOLO_PLATE'}}},
        {'modelVersionId': 2, 'artifactFormat': 'RKNN',
         'runtimeManifest': {'taskType': 'OCR', 'decoder': {'type': 'CHINESE_PLATE_CTC'}}},
    ]
    validate_bindings(MANIFEST, {'plate': 1, 'ocr': 2}, models)
    models[1]['runtimeManifest']['decoder']['type'] = 'LPRNET'
    with pytest.raises(ValueError, match='不兼容'):
        validate_bindings(MANIFEST, {'plate': 1, 'ocr': 2}, models)


def test_old_runtime_capability_rejects_new_package_before_worker_start(tmp_path, monkeypatch):
    import ai_runtime.app.capability.package_runner as module
    installed = AlgorithmPackageStore(tmp_path).install(package())
    monkeypatch.setattr(module, 'RUNTIME_CAPABILITIES', ['observation-validity-v1'])
    with pytest.raises(ValueError, match='运行能力'):
        PackageRunner(
            tmp_path, installed, MANIFEST['defaultParameters'], {'plate': 1, 'ocr': 2}, None
        )


def test_real_worker_receives_tracks_after_rectified_ocr_and_reinstall_keeps_old_package(tmp_path):
    installed = AlgorithmPackageStore(tmp_path).install(package())
    assert AlgorithmPackageStore(tmp_path).install(package()) == installed

    class Pool:
        def __init__(self):
            self.ocr_sizes = []

        async def test(self, request, image):
            if request.model_version_id == 1:
                obj = plate()
                obj['attributes'] = {}
                obj.pop('trackId')
            else:
                assert request.parameters.ocr_evidence
                self.ocr_sizes.append(image.size)
                obj = plate()
            return ModelTestResult(sourceWidth=image.width, sourceHeight=image.height,
                objects=[DetectionObject.model_validate(obj)], backend='FIXTURE', device='CPU',
                preprocessMillis=0, inferenceMillis=0, postprocessMillis=0)

    async def run():
        pool = Pool()
        config = SimpleNamespace(
            pipeline={'nodes': [{'id': 'plate', 'capabilityKey': 'model.plate'},
                                {'id': 'ocr', 'capabilityKey': 'model.ocr'}],
                      'algorithmPackage': installed},
            model_bindings={'plate': 1, 'ocr': 2},
            parameters=TaskInferenceParameters(schemaVersion='1.0'), rule=None,
        )
        inference = TaskFrameInference(config, pool, tmp_path / 'image.png')
        runner = PackageRunner(tmp_path, installed, MANIFEST['defaultParameters'],
                               config.model_bindings, pool)
        tracker = IoUTracker(motion_classes=frozenset({'license_plate'}))
        await runner.start()
        try:
            for timestamp in [0, 250, 500]:
                _, objects = await inference.infer(Image.new('RGB', (640, 480)))
                result = await runner.run(tracker.update(objects, timestamp),
                    Image.new('RGB', (640, 480)), timestamp, config.parameters)
            assert result[0].attributes['plateNumber'] == '新A12345'
            assert all(w < 640 and h < 480 for w, h in pool.ocr_sizes)
            processor = CapabilityPostprocessor(config.pipeline, config.parameters)
            candidates = processor.rule_observations(result, 500)
            assert candidates[0].track_id == 'plate:新A12345'
            assert candidates[0].attributes['provinceSource'] == 'REGION_ASSISTED'
        finally:
            await runner.close()
        # Fresh worker / offline reload starts a new voting window.
        runner = PackageRunner(tmp_path, installed, MANIFEST['defaultParameters'],
                               config.model_bindings, pool)
        await runner.start()
        try:
            result = await runner.run([DetectionObject.model_validate(plate())],
                Image.new('RGB', (640, 480)), 1000, config.parameters)
            assert result[0].attributes['ocrStatus'] == 'PENDING'
        finally:
            await runner.close()

    asyncio.run(run())


def test_live_tasks_coexist_and_image_test_cannot_borrow_live_votes(tmp_path, monkeypatch):
    from uuid import uuid4

    from test_task_image_recognition import image_request
    from test_task_manager import FakeModelPool, FakeSharedStream, request

    from ai_runtime.app.core.config import RuntimeSettings
    from ai_runtime.app.rule.contracts import RuleAst
    from ai_runtime.app.task.contracts import TaskOverlayFrame
    from ai_runtime.app.task.image_recognition import TaskImageRecognizer
    from ai_runtime.app.task.manager import CapturedFrame, TaskManager

    class Pool(FakeModelPool):
        async def test(self, value, image=None):
            obj = plate()
            obj.pop('trackId')
            if value.model_version_id == 1:
                obj['attributes'] = {}
            elif not value.parameters.ocr_evidence:
                obj['attributes'].pop('ocrEvidenceJson')
            return ModelTestResult(sourceWidth=image.width, sourceHeight=image.height,
                objects=[DetectionObject.model_validate(obj)], backend='FIXTURE', device='CPU',
                preprocessMillis=0, inferenceMillis=0, postprocessMillis=0)

    async def scenario():
        installed = AlgorithmPackageStore(tmp_path).install(package())
        pool = Pool()
        manager = TaskManager(RuntimeSettings(api_key='a-secure-runtime-key-for-tests',
            runtime_data_root=tmp_path), pool, FakeSharedStream)
        original = request(1, str(uuid4()))
        original.pipeline = {
            'schemaVersion': '1.0',
            'nodes': [
                {'id': 'plate', 'type': 'DETECTOR', 'capabilityKey': 'detector.license-plate'},
                {'id': 'ocr', 'type': 'OCR', 'capabilityKey': 'ocr.license-plate'},
                {'id': 'tracker', 'type': 'TRACKER', 'capabilityKey': 'tracker.iou'},
            ],
            'edges': [{'from': 'plate', 'to': 'ocr'}, {'from': 'ocr', 'to': 'tracker'}],
        }
        original.model_bindings = {'plate': 1, 'ocr': 2}
        original.parameters.sample_fps = 4
        original.rule_id = 1
        original.rule_version_id = 1
        original.rule = RuleAst.model_validate(MANIFEST['defaultRule'])
        enhanced = original.model_copy(deep=True, update={'task_id': 2, 'run_id': str(uuid4())})
        enhanced.pipeline = {
            'schemaVersion': '1.0', 'algorithmPackage': installed, 'edges': [],
            'nodes': [{'id': 'plate', 'type': 'DETECTOR', 'capabilityKey': 'model.plate'},
                      {'id': 'ocr', 'type': 'OCR', 'capabilityKey': 'model.ocr'}],
        }
        enhanced.parameters.algorithm = MANIFEST['defaultParameters'].copy()
        before = original.model_dump()
        events = []
        published = {task_id: asyncio.Event() for task_id in (1, 2)}

        def overlay(**values):
            result = TaskOverlayFrame(**values)
            published[values['taskId']].set()
            return result

        monkeypatch.setattr('ai_runtime.app.task.manager.TaskOverlayFrame', overlay)

        async def record(transition):
            events.append(transition)

        try:
            await manager.start_task(original)
            await manager.start_task(enhanced)
            assert manager.active_stream_count == 1
            manager._tasks[2]._evidence.start = record
            buffer = io.BytesIO()
            Image.new('RGB', (640, 480)).save(buffer, 'JPEG')
            stream_id = str(uuid4())
            for i in range(4):
                for event in published.values():
                    event.clear()
                for runner in manager._tasks.values():
                    runner.queue.put_nowait(CapturedFrame(
                        buffer.getvalue(), 1791252000000 + i * 250,
                        stream_id=stream_id, source_pts=i * 22500,
                    ))
                async with asyncio.timeout(3):
                    await asyncio.gather(*(event.wait() for event in published.values()))
                assert all(r._analyzed_frames == i + 1 for r in manager._tasks.values())
            old = manager.latest_overlay(1).objects[0].attributes
            new = manager.latest_overlay(2).objects[0].attributes
            assert old['ocrStatus'] == 'LOW_CHAR_CONFIDENCE'
            assert 'ocrEvidenceJson' not in old and 'plateNumber' not in old
            assert new['plateNumber'] == '新A12345'
            assert len(events) == 1
            assert manager._tasks[2]._confirmed_events == 1
            assert manager._tasks[1]._confirmed_events == 0
            document = {'revision': 1, 'config': enhanced.model_dump(mode='json', by_alias=True)}
            image = await TaskImageRecognizer(tmp_path, pool, None).recognize(
                image_request().model_copy(update={'task_id': 2}), document)
            attrs = image['objects'][0]['attributes']
            assert attrs['ocrVoteFrames'] == 1 and attrs['ocrStatus'] == 'PENDING'
            await manager.stop_task(2, enhanced.run_id)
            assert manager.statuses()[0].status == 'RUNNING'
            published[1].clear()
            manager._tasks[1].queue.put_nowait(CapturedFrame(
                buffer.getvalue(), 1791252001000, stream_id=stream_id, source_pts=90000,
            ))
            async with asyncio.timeout(3):
                await published[1].wait()
            assert manager.latest_overlay(1).objects[0].attributes['plateText'] == '浙A12345'
            assert manager._tasks[1].request.model_dump() == before
        finally:
            await manager.close()

    asyncio.run(scenario())
