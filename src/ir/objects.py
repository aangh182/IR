from __future__ import annotations

COCO_CATEGORIES: dict[str, tuple[str, ...]] = {
    "Người": ("person",),
    "Phương tiện": (
        "bicycle",
        "car",
        "motorcycle",
        "airplane",
        "bus",
        "train",
        "truck",
        "boat",
    ),
    "Giao thông": (
        "traffic light",
        "fire hydrant",
        "stop sign",
        "parking meter",
        "bench",
    ),
    "Động vật": (
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
    ),
    "Phụ kiện": ("backpack", "umbrella", "handbag", "tie", "suitcase"),
    "Thể thao": (
        "frisbee",
        "skis",
        "snowboard",
        "sports ball",
        "kite",
        "baseball bat",
        "baseball glove",
        "skateboard",
        "surfboard",
        "tennis racket",
    ),
    "Nhà bếp": ("bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl"),
    "Đồ ăn": (
        "banana",
        "apple",
        "sandwich",
        "orange",
        "broccoli",
        "carrot",
        "hot dog",
        "pizza",
        "donut",
        "cake",
    ),
    "Nội thất": ("chair", "couch", "potted plant", "bed", "dining table", "toilet"),
    "Thiết bị": (
        "tv",
        "laptop",
        "mouse",
        "remote",
        "keyboard",
        "cell phone",
        "microwave",
        "oven",
        "toaster",
        "sink",
        "refrigerator",
    ),
    "Đồ vật": (
        "book",
        "clock",
        "vase",
        "scissors",
        "teddy bear",
        "hair drier",
        "toothbrush",
    ),
}

CATEGORY_ORDER: tuple[str, ...] = tuple(COCO_CATEGORIES)
OTHER_CATEGORY = "Khác"

CATEGORY_BY_LABEL: dict[str, str] = {
    label: category for category, labels in COCO_CATEGORIES.items() for label in labels
}


def category_of(label: str) -> str:
    return CATEGORY_BY_LABEL.get(label.strip().lower(), OTHER_CATEGORY)


def category_rank(category: str) -> int:
    try:
        return CATEGORY_ORDER.index(category)
    except ValueError:
        return len(CATEGORY_ORDER)


def parse_object_filters(
    values: list[str | tuple[str, int]] | None,
) -> list[tuple[str, int]]:
    """Parse ["person", "car:2"] or [("person", 1)] into (label, min_count) pairs.

    Multiple entries for the same label keep the highest min_count; the result is
    sorted by label. Invalid counts fall back to 1.
    """
    parsed: dict[str, int] = {}
    for value in values or []:
        if isinstance(value, tuple):
            label = str(value[0]).strip().lower()
            count = value[1]
        else:
            text = str(value).strip().lower()
            if not text:
                continue
            label, separator, count_text = text.partition(":")
            label = label.strip()
            count = 1
            if separator:
                try:
                    count = int(count_text.strip())
                except ValueError:
                    count = 1
        if not label:
            continue
        try:
            minimum = max(1, int(count))
        except (TypeError, ValueError):
            minimum = 1
        parsed[label] = max(parsed.get(label, 0), minimum)
    return sorted(parsed.items())
