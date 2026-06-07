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
  parent_heading_level: number  // 父块粒度（几级标题=1父块）；0=全局默认
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

/**
 * 统一 SSE 词汇（后端 conversation_service.stream_turn + 各场景编排共用）。
 * 一条流：conversation → (message_start[user] → message_start[assistant] →
 *   citations? → thinking* → delta* → message_end) → done
 * 讲义生成在同一条流内重复多个 message_start[assistant]/message_end（每节一个）。
 */
export type ChatEvent =
  | { type: "conversation"; conversation_id: string; total_sections?: number }
  | {
      type: "message_start"
      role: "user" | "assistant"
      message_id: string
      metadata?: Record<string, unknown>
    }
  | { type: "citations"; citations: CitationItem[] }
  | { type: "thinking"; content: string }
  | { type: "delta"; content: string }
  | { type: "message_end"; message_id: string }
  | { type: "done"; conversation_id?: string }
  | { type: "error"; message: string }

export type ThemeMode = "light" | "dark" | "sepia"

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

// ── 课后复习讲义（磁盘文件）────────────────────────────────

export interface ReviewNote {
  section_num: number
  path: string
  content_md: string
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

// ── 检索透视 Retrieval X-Ray（v1.4.0）──────────────────────
// 对应后端 POST /api/chat/{kb_id}/retrieve-trace 的返回，结构来自
// retrieval_trace.RetrievalTrace.to_dict()。把隐藏的检索链路全揭开：
// LLM 查询规划 → 关键词(BM25)+向量 双路 → RRF 融合 → qwen3-rerank 重排。

export interface QueryPlan {
  original_question: string
  rewritten_question: string
  keywords: string[]
  semantic_query: string
  source: "llm" | "fallback"
}

/** 双路召回的单条命中（vector_hits / keyword_hits 共用；matched_* 仅关键词路有）。 */
export interface XrayHit {
  rank: number
  child_chunk_id: string
  parent_chunk_id?: string
  doc_id: string
  chunk_type?: string
  header_path: string[]
  text: string
  score: number
  matched_keywords?: string[]   // 含 ≥1 命中 token 的规划关键词（点亮 chip）
  matched_tokens?: string[]     // 实际命中的 token（按词边界高亮片段）
}

/** RRF 融合表的一行：两路 rank/score 汇成 rrf_score。 */
export interface XrayFusionRow {
  rank: number
  child_chunk_id: string
  doc_id: string
  header_path: string[]
  text: string
  vec_rank: number | null
  vec_score: number | null
  kw_rank: number | null
  kw_score: number | null
  rrf_score: number
}

/** 重排后的一行：prev_rank/delta 记录相对融合序的位次变化。 */
export interface XrayRerankRow {
  rank: number
  prev_rank: number | null
  delta: number | null
  child_chunk_id: string
  parent_chunk_id: string
  doc_id: string
  chunk_type: string
  header_path: string[]
  text: string
  rerank_score: number
}

export interface RetrievalTrace {
  plan: QueryPlan
  vector_hits: XrayHit[]
  keyword_hits: XrayHit[]
  fusion: XrayFusionRow[]
  reranked: XrayRerankRow[]
  counts: { vector: number; keyword: number; fused: number; final: number }
  timings_ms: { plan: number; recall: number; fuse: number; rerank: number; total: number }
  rerank_degraded: boolean
}

export interface DocMeta {
  filename: string
  source_format: string
}

export interface RetrievalTraceResponse {
  query: string
  kb_id: string
  trace: RetrievalTrace
  docs: Record<string, DocMeta>
}

// ── 解析透视 Parse X-Ray（v1.4.0 Phase 3）─────────────────────
// 对应后端只读检视接口 GET /api/documents/{kb}/{doc}/ir、/chunks、/asset。
// 把 MinerU JSON 解析 → 结构感知 → LLM 文档树重建 → 坐标锚定 →
// 父子结构感知切片 → 图片 VLM 多模态适配，整条隐藏流水线揭开成可视化。

/** IR 块类型（与后端 models_ir.BlockType 对齐）。 */
export type IRBlockType =
  | "title" | "paragraph" | "list" | "code" | "table" | "image" | "equation"

/** IR 投影里的单个版面块（坐标已归一到 0~1000）。 */
export interface IRBlock {
  block_id: string
  page_idx: number          // 0-based
  order_in_doc: number
  order_in_page: number
  section_id: string
  header_path: string[]
  type: IRBlockType | string
  role: string              // main / header / footer / caption …
  text: string
  bbox_norm1000: number[]   // [x0,y0,x1,y1]，非 PDF 文档可能全 0
  bbox_page: number[]
  assets: string[]          // asset_id 列表
  title_level: number | null
  table_html: string | null
  vlm_description: string    // 我们自己 VLM 生成的图片描述（enriched 才有）
}

/** LLM 重建后的 section 节点（文档树）。 */
export interface IRSection {
  section_id: string
  parent_section_id: string | null
  level: number
  title: string
  header_path: string[]
  synthetic: boolean
  page_span: number[]
  child_section_ids: string[]
  block_ids: string[]
}

export interface IRPage {
  page_idx: number
  width: number | null
  height: number | null
}

export interface IRDocumentMeta {
  title: string
  language: string
  page_count: number
  source_format: string
  origin_pdf_path: string
  has_multimodal: boolean
  has_table: boolean
  has_code: boolean
  has_equation: boolean
}

/** 父切片按 section × page 的 bbox 并集（左栏父块大框）。 */
export interface SectionBboxEntry {
  page_idx: number
  bbox_norm1000: number[]
}

export interface IRResponse {
  doc_id: string
  kb_id: string
  document: IRDocumentMeta
  enriched: boolean
  pages: IRPage[]
  sections: IRSection[]
  blocks: IRBlock[]
  section_bbox: Record<string, SectionBboxEntry[]>
}

/** 父切片（以 section 为边界，回答阶段补全大上下文）。 */
export interface ParentChunkRow {
  parent_chunk_id: string
  doc_id: string
  section_id: string
  header_path: string[]
  title: string
  page_span: number[]
  block_ids: string[]
  text_for_generation: string
  assets: string[]
}

/** 子切片（面向向量检索的小粒度块）。 */
export interface ChildChunkRow {
  child_chunk_id: string
  parent_chunk_id: string
  doc_id: string
  section_id: string
  header_path: string[]
  chunk_type: string
  page_span: number[]
  source_block_ids: string[]
  bbox_norm1000: number[][]
  bbox_page: number[][]
  retrieval_text: string
  embedding_text: string
  assets: string[]
}

export interface ChunksResponse {
  doc_id: string
  kb_id: string
  parents: ParentChunkRow[]
  children: ChildChunkRow[]
  counts: { parents: number; children: number }
}

// ── 父块自定义索引（v1.5.0）─────────────────────────────────

// 图/表描述不在此单列——基础切片管线已让每图/表各成独立子块按描述索引（见 child_chunker），故无 image_desc/table_desc。
export type ExtraIndexKind = "summary" | "hypo_question" | "custom"

/** 推测问题预答等附加数据 */
export interface ExtraIndexPayload {
  questions?: string[]
  answers?: string[]
}

/** 挂在父块上的一条自定义索引（启用即物化为虚拟子块接入混合检索）。 */
export interface ExtraIndex {
  index_id: string
  doc_id: string
  parent_chunk_id: string
  section_id: string
  kind: ExtraIndexKind
  title: string
  index_text: string
  payload: ExtraIndexPayload
  enabled: boolean
  source: string            // "auto" | "user"
  child_chunk_id: string
  created_at: string
  updated_at: string
}

export interface DocIndexesResponse {
  doc_id: string
  kb_id: string
  items: ExtraIndex[]
  by_parent: Record<string, ExtraIndex[]>
}
