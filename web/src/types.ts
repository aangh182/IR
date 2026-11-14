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

export type ModelInfo = {
  name: string
  model: string
  dim: number
  encoder: string
  available: boolean
  keyframes: number | null
  default: boolean
}

export type ObjectFacet = {
  label: string
  keyframes: number
  videos: number
}

export type SearchResponse = {
  query_id: string
  query: string
  translated_query: string
  model: string
  elapsed_ms: number
  results: Hit[]
  dres_payload: unknown
}

export type DresTask = {
  name: string
  task_group: string
  task_type: string
  duration: number | null
  is_visual: boolean
}

export type DresStatus = {
  configured: boolean
  base_url?: string
  user: { id: string; username: string; role: string } | null
  evaluation: { id: string; name: string; status: string; type: string } | null
  task: DresTask | null
  error?: string
}

export type DresSubmitKind = 'kis' | 'vkis' | 'qa' | 'trake' | 'raw'

export type DresSubmitRequest = {
  kind: DresSubmitKind
  video_id?: string | null
  ts_ms?: number | null
  answer?: string | null
  frame_ids?: number[] | null
  payload?: unknown
  task_id?: string | null
}

export type DresSubmitResult = {
  status?: boolean
  submission?: string
  description?: string
  http_status?: number
  category?: 'correct' | 'wrong' | 'review' | 'unknown'
  answers?: unknown[]
  detail?: string
}
