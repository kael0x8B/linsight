from dataclasses import dataclass
from typing import Literal

type ModelAdapterName = Literal[
    "person_detection_v1",
    "safety_helmet_v1",
    "sleeping_on_duty_v1",
    "license_plate_v1",
    "reflective_vest_v1",
    "flame_detection_v1",
    "smoking_detection_v1",
    "phone_call_detection_v1",
    "road_waterlogging_v1",
    "face_mask_v1",
    "fall_detection_v1",
    "face_detection_v1",
    "vehicle_detection_v1",
    "coco_detection_v1",
    "unified_ppe_detection_v1",
    "smoking_phone_detection_v1",
    "flame_smoke_detection_v1",
    "garbage_debris_detection_v1",
    "vehicle_type_detection_v1",
    "human_pose_v1",
    "video_action_v1",
    "license_plate_ocr_v1",
    "abandoned_object_v1",
    "face_embedding_v1",
    "face_liveness_v1",
    "general_ocr_v1",
    "meter_reading_v1",
    "open_vocabulary_v1",
    "general_segmentation_v1",
    "video_quality_v1",
]


@dataclass(frozen=True)
class AdapterDefinition:
    name: str
    class_labels: tuple[str, ...]


# This registry is an execution contract, not a claim that an asset is present or licensed.
# Every adapter consumes the normalized [N, 6] output described in MODEL_EXECUTION_PROTOCOL_V1.
ADAPTERS: dict[str, AdapterDefinition] = {
    "person_detection_v1": AdapterDefinition("person_detection_v1", ("person",)),
    "safety_helmet_v1": AdapterDefinition(
        "safety_helmet_v1", ("person", "helmet", "no_helmet", "unknown")
    ),
    "sleeping_on_duty_v1": AdapterDefinition("sleeping_on_duty_v1", ("sleeping",)),
    "license_plate_v1": AdapterDefinition("license_plate_v1", ("license_plate",)),
    "reflective_vest_v1": AdapterDefinition(
        "reflective_vest_v1", ("person", "vest", "no_vest", "unknown")
    ),
    "flame_detection_v1": AdapterDefinition("flame_detection_v1", ("flame",)),
    "smoking_detection_v1": AdapterDefinition("smoking_detection_v1", ("smoking",)),
    "phone_call_detection_v1": AdapterDefinition("phone_call_detection_v1", ("phone_call",)),
    "road_waterlogging_v1": AdapterDefinition("road_waterlogging_v1", ("road_waterlogging",)),
    "face_mask_v1": AdapterDefinition("face_mask_v1", ("face_mask", "no_face_mask")),
    "fall_detection_v1": AdapterDefinition("fall_detection_v1", ("fall",)),
    "face_detection_v1": AdapterDefinition("face_detection_v1", ("face",)),
    "vehicle_detection_v1": AdapterDefinition(
        "vehicle_detection_v1", ("car", "truck", "bus", "motorcycle")
    ),
    "coco_detection_v1": AdapterDefinition(
        "coco_detection_v1",
        (
            "person",
            "bicycle",
            "car",
            "motorcycle",
            "airplane",
            "bus",
            "train",
            "truck",
            "boat",
            "traffic_light",
            "fire_hydrant",
            "stop_sign",
            "parking_meter",
            "bench",
            "bird",
            "cat",
            "dog",
            "horse",
            "sheep",
            "cow",
            "elephant",
            "bear",
            "zebra",
            "giraffe",
            "backpack",
            "umbrella",
            "handbag",
            "tie",
            "suitcase",
            "frisbee",
            "skis",
            "snowboard",
            "sports_ball",
            "kite",
            "baseball_bat",
            "baseball_glove",
            "skateboard",
            "surfboard",
            "tennis_racket",
            "bottle",
            "wine_glass",
            "cup",
            "fork",
            "knife",
            "spoon",
            "bowl",
            "banana",
            "apple",
            "sandwich",
            "orange",
            "broccoli",
            "carrot",
            "hot_dog",
            "pizza",
            "donut",
            "cake",
            "chair",
            "couch",
            "potted_plant",
            "bed",
            "dining_table",
            "toilet",
            "tv",
            "laptop",
            "mouse",
            "remote",
            "keyboard",
            "cell_phone",
            "microwave",
            "oven",
            "toaster",
            "sink",
            "refrigerator",
            "book",
            "clock",
            "vase",
            "scissors",
            "teddy_bear",
            "hair_drier",
            "toothbrush",
        ),
    ),
    "unified_ppe_detection_v1": AdapterDefinition(
        "unified_ppe_detection_v1",
        (
            "person",
            "helmet",
            "no_helmet",
            "vest",
            "no_vest",
            "face_mask",
            "no_face_mask",
            "workwear",
            "no_workwear",
            "unknown",
        ),
    ),
    "smoking_phone_detection_v1": AdapterDefinition(
        "smoking_phone_detection_v1",
        ("person", "cigarette", "smoking", "cell_phone", "phone_call", "playing_phone"),
    ),
    "flame_smoke_detection_v1": AdapterDefinition(
        "flame_smoke_detection_v1", ("flame", "smoke", "dense_smoke")
    ),
    "garbage_debris_detection_v1": AdapterDefinition(
        "garbage_debris_detection_v1", ("garbage", "debris", "pile", "obstruction")
    ),
    "vehicle_type_detection_v1": AdapterDefinition(
        "vehicle_type_detection_v1",
        (
            "sedan",
            "suv",
            "van",
            "small_truck",
            "box_truck",
            "medium_truck",
            "heavy_truck",
            "trailer",
            "engineering_vehicle",
        ),
    ),
    "human_pose_v1": AdapterDefinition("human_pose_v1", ("person",)),
    "video_action_v1": AdapterDefinition(
        "video_action_v1", ("fighting", "running", "sleeping", "phone", "smoking")
    ),
    "license_plate_ocr_v1": AdapterDefinition("license_plate_ocr_v1", ("license_plate",)),
    "abandoned_object_v1": AdapterDefinition("abandoned_object_v1", ("object",)),
    "face_embedding_v1": AdapterDefinition("face_embedding_v1", ("face",)),
    "face_liveness_v1": AdapterDefinition("face_liveness_v1", ("live", "spoof")),
    "general_ocr_v1": AdapterDefinition("general_ocr_v1", ("text",)),
    "meter_reading_v1": AdapterDefinition("meter_reading_v1", ("meter",)),
    "open_vocabulary_v1": AdapterDefinition("open_vocabulary_v1", ("object",)),
    "general_segmentation_v1": AdapterDefinition("general_segmentation_v1", ("object",)),
    "video_quality_v1": AdapterDefinition(
        "video_quality_v1", ("normal", "blur", "dark", "bright", "occluded")
    ),
}


def require_adapter(name: str) -> AdapterDefinition:
    try:
        return ADAPTERS[name]
    except KeyError as error:
        raise ValueError(f"unsupported model adapter: {name}") from error
