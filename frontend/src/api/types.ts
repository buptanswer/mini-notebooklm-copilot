// API TypeScript 类型定义

export interface KBInfo {
  kb_id: string
  name: string
  description: string
  created_at: string
  updated_at: string
  file_count: number
  status: string
}

export type DocStatus =
  | "uploaded"
  | "parsing"
  | "needs_review"
  | "indexed"
  | "failed"

export interface DocInfo {
  doc_id: string
  kb_id: string
  filename: string
  relative_path: string
  source_format: string
  file_size: number
  page_count: number
  status: DocStatus
  warnings: string   // 非空时表示有解析警告
  origin_pdf_path: string
  created_at: string
  updated_at: string
}

export type TaskStatus = "created" | "pending" | "running" | "done" | "failed"

export interface TaskInfo {
  task_id: string
  doc_id: string
  task_type: string
  status: TaskStatus
  progress: number   // 0.0 ~ 1.0
  error_msg: string
  created_at: string
  updated_at: string
}

// ── Chat SSE 事件 ──────────────────────────────────────────

export interface CitationItem {
  index: number
  child_chunk_id: string
  parent_chunk_id: string
  doc_id: string
  header_path: string[]
  page_span_start: number
  page_span_end: number
  bbox_norm1000: number[][]
  bbox_page: number[][]
  anchor_origin_pdf_path: string
  retrieval_text: string
  score: number
}

export type ChatEvent =
  | { type: "citations"; citations: CitationItem[] }
  | { type: "delta"; content: string }
  | { type: "thinking"; content: string }
  | { type: "end" }
  | { type: "error"; message: string }

// ── Search 结果 ────────────────────────────────────────────

export interface SearchResultItem {
  rank: number
  child_chunk_id: string
  parent_chunk_id: string
  doc_id: string
  header_path: string[]
  page_span_start: number
  page_span_end: number
  bbox_norm1000: number[][]
  bbox_page: number[][]
  anchor_origin_pdf_path: string
  retrieval_text: string
  score: number
  source: string
}
