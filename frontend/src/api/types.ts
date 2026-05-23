// API TypeScript 类型定义

export type KBType = "general" | "course"

export interface KBInfo {
  kb_id: string
  name: string
  description: string
  kb_type: KBType
  bound_folder_path: string
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
  | "text_only"
  | "missing"

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
  folder_category: string  // recording / slides / homework / notice / review_note / ''
  bound_file_path: string  // 绑定文件夹模式下的文件路径
  created_at: string
  updated_at: string
}

export type TaskStatus = "created" | "running" | "done" | "failed"

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

// ── 多轮对话 ────────────────────────────────────────────────

export interface MessageInfo {
  message_id: string
  conversation_id: string
  role: "system" | "user" | "assistant"
  content: string
  thinking: string
  sequence_num: number
  citations: CitationItem[]
  metadata: Record<string, unknown>
  created_at: string
}

export interface ConversationInfo {
  conversation_id: string
  kb_id: string
  scenario: string
  title: string
  parent_conversation_id: string
  fork_from_message_id: string
  metadata: Record<string, unknown>
  enable_thinking: boolean
  created_at: string
  updated_at: string
  messages?: MessageInfo[]
}

// ── 课程管家 ────────────────────────────────────────────────

export interface AssessmentInfo {
  exam_ratio: number
  hw_ratio: number
  attendance_ratio: number
  description: string
}

export interface DeadlineItem {
  name: string
  date_text: string
  description: string
  date?: string
  days_left?: number | null
}

export interface CourseInfoCard {
  card_id: string
  kb_id: string
  course_name: string
  instructor: string
  contact: string
  assessment: AssessmentInfo
  deadlines: DeadlineItem[]
  deadlines_normalized: DeadlineItem[]
  important_notes: string
  created_at: string
  updated_at: string
}

// ── 课后复习 ────────────────────────────────────────────────

export interface ReviewDateInfo {
  date: string
  section_count: number
  has_notes: boolean
}

export interface ReviewSectionInfo {
  section_num: number
  txt_doc_id: string
  txt_path: string
  note_doc_id: string | null
  note_path: string | null
}

// ── 文件夹同步 ──────────────────────────────────────────────

export interface SyncDiff {
  added: Array<{doc_id: string; filename: string; relative_path: string; folder_category: string; source_format: string; status: string}>
  removed: Array<{doc_id: string; bound_file_path: string}>
  unchanged: number
}

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
