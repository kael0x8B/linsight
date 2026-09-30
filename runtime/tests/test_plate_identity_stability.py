from ai_runtime.app.capability.postprocess import CapabilityPostprocessor
from ai_runtime.app.capability.tracker import IoUTracker
from ai_runtime.app.model.contracts import DetectionObject
from ai_runtime.app.task.contracts import TaskInferenceParameters


def plate(text='吉WD0010', **attributes):
    return DetectionObject.model_validate({
        'class': 'license_plate', 'confidence': .9, 'trackId': 'one',
        'bbox': {'x': .3, 'y': .4, 'width': .15, 'height': .08},
        'attributes': {'plateText': text, 'ocrConfidence': .98,
                       'ocrMinCharConfidence': .96, **attributes},
    })


def test_one_inserted_or_deleted_character_does_not_create_new_physical_track():
    tracker = IoUTracker(motion_classes=frozenset({'license_plate'}))
    tracks = [tracker.update([plate(text)], i * 200)[0].track_id
              for i, text in enumerate(['吉WD0010', '吉WD0010F', '吉WD0010', '吉VD0010'])]
    assert len(set(tracks)) == 1
    other = plate('皖A12345')
    other.bbox.x = .6
    assert tracker.update([other], 800)[0].track_id != tracks[0]


def test_stationary_plate_can_confirm_across_short_decode_gaps():
    tracker = IoUTracker(
        motion_classes=frozenset({'license_plate'}),
        stationary_reacquire_millis=4000,
    )
    processor = CapabilityPostprocessor(
        {'nodes': [{'capabilityKey': 'ocr.license-plate'}]},
        TaskInferenceParameters(schemaVersion='1.0', ocrMinVotes=3,
                                ocrVoteFrames=5, ocrVoteMaxAgeSeconds=10),
    )
    tracks = []
    for timestamp in (0, 2800, 5400):
        tracked = tracker.update([plate(plateCropWidth=450)], timestamp)
        tracks.append(tracked[0].track_id)
        result = processor.after_tracking(tracked, timestamp)
    assert len(set(tracks)) == 1
    assert result[0].attributes['ocrStatus'] == 'CONFIRMED'


def test_stationary_reacquisition_does_not_merge_conflicting_or_moved_plates():
    tracker = IoUTracker(
        motion_classes=frozenset({'license_plate'}),
        stationary_reacquire_millis=4000,
    )
    original = tracker.update([plate(plateCropWidth=450)], 0)[0].track_id
    assert tracker.update([plate('吉VD0010', plateCropWidth=450)], 2800)[0].track_id != original
    moved = plate(plateCropWidth=450)
    moved.bbox.x = 0.7
    assert tracker.update([moved], 3000)[0].track_id != original


def test_short_decode_gap_does_not_extend_a_small_uncertain_plate_track():
    tracker = IoUTracker(
        motion_classes=frozenset({'license_plate'}),
        stationary_reacquire_millis=4000,
    )
    original = tracker.update([plate(plateCropWidth=150)], 0)[0].track_id
    assert tracker.update([plate(plateCropWidth=150)], 2800)[0].track_id != original


def test_plurality_of_two_in_five_cannot_confirm_a_conflicting_number():
    processor = CapabilityPostprocessor(
        {'nodes': [{'capabilityKey': 'ocr.license-plate'}]},
        TaskInferenceParameters(schemaVersion='1.0', ocrMinVotes=2, ocrVoteFrames=5),
    )
    for i, text in enumerate(['吉BD0010', '吉VD0010', '吉WD0010', '吉D0010F', '吉WD0010']):
        result = processor.after_tracking([plate(text)], i * 200)
    assert result[0].attributes['ocrVoteCount'] == 2
    assert result[0].attributes['ocrStatus'] == 'PENDING'
    assert not processor.event_candidates(result)
    result = processor.after_tracking([plate()], 1000)
    assert result[0].attributes['plateNumber'] == '吉WD0010'


def test_auxiliary_layout_cannot_bypass_configured_character_threshold():
    processor = CapabilityPostprocessor(
        {'nodes': [{'capabilityKey': 'ocr.license-plate'}]},
        TaskInferenceParameters(schemaVersion='1.0', ocrMinVotes=3),
    )
    for i in range(5):
        result = processor.after_tracking([plate(
            '吉VD0010', ocrMinCharConfidence=.69,
            ocrLayout='YELLOW_SIDEBAR', plateCropRetried=True,
        )], i * 200)
        assert result[0].attributes['ocrStatus'] == 'LOW_CHAR_CONFIDENCE'
        assert not processor.event_candidates(result)
