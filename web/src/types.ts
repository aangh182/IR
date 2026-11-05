export type Health = {
  status: string
  version: string
  db: string
  db_ready: boolean
  index_ready: boolean
  index_count: number | null
  index_model: string | null
}

export type Stats = {
  videos: number
  shots: number
  keyframes: number
  follow_frames: number
  asr_segments: number
}

export type FrameOption = {
  ts_ms: number
  start_ms: number
  end_ms: number
  url: string
  is_keyframe: boolean
}

export type Hit = {
  video_id: string
  shot_idx: number
  start_ms: number
  end_ms: number
  score: number
  confidence: number
  keyframe_url: string
  frames: FrameOption[]
  evidence: {
    ocr: string
    asr: string
    objects: string[]
  }
}

export type SearchResponse = {
  query_id: string
  elapsed_ms: number
  results: Hit[]
  dres_payload: unknown
}
