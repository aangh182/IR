from __future__ import annotations

from contextlib import closing

from ir.store.db import (
    bump_generation,
    compact_video,
    connect,
    delete_follow_frames,
    get_stats,
    init_db,
    insert_follow_frame,
    insert_keyframe,
    keyframe_uids_with_objects,
    load_follow_frames,
    upsert_video,
)
from ir.types import FollowFrame, Keyframe, Video


def _video(video_id: str) -> Video:
    return Video(
        video_id=video_id,
        path=f"/videos/{video_id}.mp4",
        duration_ms=60_000,
        fps=25.0,
        width=1920,
        height=1080,
        has_audio=True,
    )


def test_init_and_active_counts(tmp_path) -> None:
    db_path = init_db(tmp_path / "metadata.sqlite")

    with closing(connect(db_path)) as conn:
        upsert_video(conn, _video("L21_V001"))
        conn.execute(
            "INSERT INTO shots (video_id, generation, shot_idx, start_ms, end_ms) "
            "VALUES ('L21_V001', 0, 0, 0, 5000)"
        )
        conn.execute(
            "INSERT INTO keyframes (video_id, generation, shot_idx, kf_idx, ts_ms, path) "
            "VALUES ('L21_V001', 0, 0, 0, 2500, 'a.jpg')"
        )
        conn.commit()

        counts = get_stats(conn)

    assert counts == {
        "videos": 1,
        "shots": 1,
        "keyframes": 1,
        "follow_frames": 0,
        "asr_segments": 0,
    }


def test_keyframe_index_is_unique_per_shot(tmp_path) -> None:
    db_path = init_db(tmp_path / "metadata.sqlite")

    with closing(connect(db_path)) as conn:
        upsert_video(conn, _video("L21_V001"))
        for shot_idx in (0, 1):
            insert_keyframe(
                conn,
                Keyframe(
                    video_id="L21_V001",
                    shot_idx=shot_idx,
                    kf_idx=0,
                    ts_ms=1000 * (shot_idx + 1),
                    path=f"keyframes/{shot_idx}.jpg",
                ),
            )

        assert get_stats(conn)["keyframes"] == 2


def test_reindex_is_append_only_then_compact(tmp_path) -> None:
    db_path = init_db(tmp_path / "metadata.sqlite")

    with closing(connect(db_path)) as conn:
        upsert_video(conn, _video("L21_V001"))
        conn.execute(
            "INSERT INTO shots (video_id, generation, shot_idx, start_ms, end_ms) "
            "VALUES ('L21_V001', 0, 0, 0, 5000)"
        )
        conn.execute(
            "INSERT INTO keyframes (video_id, generation, shot_idx, kf_idx, ts_ms, path) "
            "VALUES ('L21_V001', 0, 0, 0, 2500, 'a.jpg')"
        )
        conn.execute(
            "INSERT INTO asr_segments (video_id, generation, seg_idx, start_ms, end_ms, text) "
            "VALUES ('L21_V001', 0, 0, 0, 5000, 'xin chào')"
        )
        conn.commit()

        assert bump_generation(conn, "L21_V001") == 1
        assert get_stats(conn) == {
            "videos": 1,
            "shots": 0,
            "keyframes": 0,
            "follow_frames": 0,
            "asr_segments": 0,
        }

        conn.execute(
            "INSERT INTO shots (video_id, generation, shot_idx, start_ms, end_ms) "
            "VALUES ('L21_V001', 1, 0, 0, 4000)"
        )
        conn.commit()
        assert get_stats(conn)["shots"] == 1

        deleted = compact_video(conn, "L21_V001")

    assert deleted == {
        "keyframes": 1,
        "follow_frames": 0,
        "shots": 1,
        "asr_segments": 1,
    }


def test_object_filter_chunks_large_uid_lists(tmp_path) -> None:
    db_path = init_db(tmp_path / "metadata.sqlite")

    with closing(connect(db_path)) as conn:
        assert keyframe_uids_with_objects(conn, list(range(1, 2501)), ["person"]) == set()


def test_follow_frames_roundtrip(tmp_path) -> None:
    db_path = init_db(tmp_path / "metadata.sqlite")

    with closing(connect(db_path)) as conn:
        upsert_video(conn, _video("L21_V001"))
        for frame_idx in range(2):
            insert_follow_frame(
                conn,
                FollowFrame(
                    video_id="L21_V001",
                    shot_idx=0,
                    kf_idx=0,
                    frame_idx=frame_idx,
                    ts_ms=3000 + frame_idx * 500,
                    path=f"follow_frames/L21_V001/g0/000000_000_{frame_idx:03d}.jpg",
                ),
            )

        assert get_stats(conn)["follow_frames"] == 2
        loaded = load_follow_frames(conn, "L21_V001", 0, shot_idx=0)
        assert [frame.ts_ms for frame in loaded] == [3000, 3500]
        assert load_follow_frames(conn, "L21_V001", 0, shot_idx=1) == []

        assert delete_follow_frames(conn, "L21_V001", 0) == 2
        assert get_stats(conn)["follow_frames"] == 0
