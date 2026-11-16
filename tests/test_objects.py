from __future__ import annotations

from ir.objects import category_of, parse_object_filters


def test_parse_object_filters_accepts_labels_and_counts() -> None:
    assert parse_object_filters(["car", "person"]) == [("car", 1), ("person", 1)]
    assert parse_object_filters(["Car:3", "person"]) == [("car", 3), ("person", 1)]
    assert parse_object_filters(["car:0", "car:2"]) == [("car", 2)]
    assert parse_object_filters(["car:abc", " ", ""]) == [("car", 1)]
    assert parse_object_filters(None) == []


def test_category_of_groups_coco_labels() -> None:
    assert category_of("person") == "Người"
    assert category_of("car") == "Phương tiện"
    assert category_of("toaster") == "Thiết bị"
    assert category_of("not-a-coco-label") == "Khác"
