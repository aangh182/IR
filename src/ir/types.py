from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Video(BaseModel):
    video_id: str
    path: str
    duration_ms: int
    fps: float | None = None
    width: int | None = None
    height: int | None = None
    has_audio: bool = False


class Shot(BaseModel):
    video_id: str
    shot_idx: int
    start_ms: int
    end_ms: int
    scene_score: float | None = None


class Keyframe(BaseModel):
    video_id: str
    shot_idx: int
    kf_idx: int
    ts_ms: int
    path: str
    kf_uid: int | None = None
    generation: int = 0
    ocr_text: str = ""
    objects: list[str] = Field(default_factory=list)


class FollowFrame(BaseModel):
    video_id: str
    shot_idx: int
    kf_idx: int
    frame_idx: int
    ts_ms: int
    path: str
    generation: int = 0


class FrameOption(BaseModel):
    ts_ms: int
    start_ms: int
    end_ms: int
    url: str
    is_keyframe: bool = False


class Evidence(BaseModel):
    ocr: str = ""
    asr: str = ""
    objects: list[str] = Field(default_factory=list)


class Hit(BaseModel):
    video_id: str
    shot_idx: int
    start_ms: int
    end_ms: int
    score: float
    confidence: float
    kf_uid: int | None = None
    keyframe_url: str = ""
    is_boilerplate: bool = False
    frames: list[FrameOption] = Field(default_factory=list)
    evidence: Evidence = Field(default_factory=Evidence)


class DresAnswer(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    media_item_name: str = Field(alias="mediaItemName")
    start: int
    end: int


class DresAnswerSet(BaseModel):
    answers: list[DresAnswer]


class DresPayload(BaseModel):
    answerSets: list[DresAnswerSet]


class SearchResponse(BaseModel):
    query_id: str
    query: str = ""
    translated_query: str = ""
    model: str = ""
    elapsed_ms: int
    results: list[Hit] = Field(default_factory=list)
    dres_payload: DresPayload | None = None
