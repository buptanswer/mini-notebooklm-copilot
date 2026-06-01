// API 客户端函数

import type {
  ChatEvent,
  ConversationInfo,
  CourseInfoCard,
  DeadlineItem,
  DocInfo,
  KBInfo,
  KBType,
  ReviewDateInfo,
  ReviewNote,
  ReviewSectionInfo,
  SearchResultItem,
  SyncDiff,
  TaskInfo,
} from "./types"

const BASE = "/api"

// ── 工具 ──────────────────────────────────────────────────

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const data = await res.json()
      detail = data.detail || detail
    } catch { /* ignore */ }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

// ── 知识库 ─────────────────────────────────────────────────

export async function listKBs(): Promise<KBInfo[]> {
  const res = await fetch(`${BASE}/kb`)
  const data = await handleResponse<{ items: KBInfo[] }>(res)
  return data.items
}

export async function getKB(kbId: string): Promise<KBInfo> {
  const res = await fetch(`${BASE}/kb/${kbId}`)
  return handleResponse<KBInfo>(res)
}

export async function createKB(
  name: string,
  description = "",
  kb_type: KBType = "general",
  bound_folder_path = "",
): Promise<KBInfo> {
  const res = await fetch(`${BASE}/kb`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description, kb_type, bound_folder_path }),
  })
  return handleResponse<KBInfo>(res)
}

export async function updateKB(
  kbId: string,
  fields: { name?: string; description?: string; kb_type?: KBType; bound_folder_path?: string },
): Promise<KBInfo> {
  const res = await fetch(`${BASE}/kb/${kbId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  })
  return handleResponse<KBInfo>(res)
}

export async function deleteKB(kbId: string): Promise<void> {
  const res = await fetch(`${BASE}/kb/${kbId}`, { method: "DELETE" })
  await handleResponse<unknown>(res)
}

// ── 文档 ───────────────────────────────────────────────────

export async function listDocuments(kbId: string): Promise<DocInfo[]> {
  const res = await fetch(`${BASE}/documents/${kbId}`)
  const data = await handleResponse<{ items: DocInfo[] }>(res)
  return data.items
}

export async function getDocument(kbId: string, docId: string): Promise<DocInfo> {
  const res = await fetch(`${BASE}/documents/${kbId}/${docId}`)
  return handleResponse<DocInfo>(res)
}

export async function uploadDocument(
  kbId: string,
  file: File,
  relativePath?: string,
): Promise<DocInfo> {
  const form = new FormData()
  form.append("file", file)
  if (relativePath) form.append("relative_path", relativePath)
  const res = await fetch(`${BASE}/documents/${kbId}/upload`, {
    method: "POST",
    body: form,
  })
  return handleResponse<DocInfo>(res)
}

export async function triggerParse(kbId: string, docId: string): Promise<void> {
  const res = await fetch(`${BASE}/documents/${kbId}/${docId}/parse`, { method: "POST" })
  await handleResponse<unknown>(res)
}

/** 索引文本文档（txt/md，录音转写不可索引）到检索库。 */
export async function indexTextDoc(kbId: string, docId: string): Promise<void> {
  const res = await fetch(`${BASE}/documents/${kbId}/${docId}/index-text`, { method: "POST" })
  await handleResponse<unknown>(res)
}

export async function deleteDocument(kbId: string, docId: string): Promise<void> {
  const res = await fetch(`${BASE}/documents/${kbId}/${docId}`, { method: "DELETE" })
  await handleResponse<unknown>(res)
}

/** 获取 origin PDF 的 URL（直接在 iframe 中使用）*/
export function getOriginPdfUrl(kbId: string, docId: string): string {
  return `${BASE}/documents/${kbId}/${docId}/origin-pdf`
}

// ── 任务 ───────────────────────────────────────────────────

export async function listAllTasks(limit = 50): Promise<TaskInfo[]> {
  const res = await fetch(`${BASE}/tasks?limit=${limit}`)
  const data = await handleResponse<{ items: TaskInfo[] }>(res)
  return data.items
}

export async function listTasksByDoc(docId: string): Promise<TaskInfo[]> {
  const res = await fetch(`${BASE}/tasks/doc/${docId}`)
  const data = await handleResponse<{ items: TaskInfo[] }>(res)
  return data.items
}

// ── 检索（不生成）─────────────────────────────────────────

export async function searchDocuments(
  kbId: string,
  query: string,
  topK = 5,
): Promise<SearchResultItem[]> {
  const res = await fetch(`${BASE}/chat/${kbId}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k: topK }),
  })
  const data = await handleResponse<{ results: SearchResultItem[] }>(res)
  return data.results
}

// ════════════════════════════════════════════════════════════
// 统一流式 SSE：一个解析器服务所有对话端点（统一 ChatEvent 词汇）
// ════════════════════════════════════════════════════════════

export interface StreamHandlers {
  onEvent: (e: ChatEvent) => void
  onError?: (err: Error) => void
  onDone?: () => void
}

/** POST 一个端点并按行解析 SSE，逐事件回调；返回 abort 函数。 */
function runSSE(url: string, body: unknown, h: StreamHandlers): () => void {
  const controller = new AbortController()

  const run = async () => {
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      })
      if (!res.ok) {
        let detail = `HTTP ${res.status}`
        try { detail = (await res.json()).detail || detail } catch { /* ignore */ }
        throw new Error(detail)
      }
      const reader = res.body!.getReader()
      const decoder = new TextDecoder()
      let buf = ""
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split("\n")
        buf = lines.pop() ?? ""
        for (const line of lines) {
          if (!line.startsWith("data:")) continue
          const data = line.slice(5).trim()
          if (!data || data === "[DONE]") continue
          try {
            const ev = JSON.parse(data) as ChatEvent
            h.onEvent(ev)
            if (ev.type === "done") { h.onDone?.(); return }
          } catch { /* ignore malformed */ }
        }
      }
      h.onDone?.()
    } catch (err) {
      if ((err as Error).name !== "AbortError") h.onError?.(err as Error)
    }
  }

  run()
  return () => controller.abort()
}

/** 通用 / 课程管家 / 任意会话内发送一条消息（统一原语）。 */
export function streamSend(
  convId: string,
  content: string,
  opts: StreamHandlers & {
    ragMode?: boolean
    topK?: number
    extraSystem?: string
    enableThinking?: boolean
    metadata?: Record<string, unknown>
  },
): () => void {
  const { ragMode, topK, extraSystem, enableThinking, metadata, ...h } = opts
  return runSSE(`${BASE}/conversations/${convId}/send`, {
    content,
    rag_mode: ragMode ?? false,
    top_k: topK ?? 5,
    extra_system: extraSystem,
    enable_thinking: enableThinking,
    metadata: metadata ?? {},
  }, h)
}

/** 模块七：逐节生成讲义（一条流内多个 message_start/message_end）。 */
export function streamReviewGenerate(
  kbId: string,
  params: {
    date: string
    course_name?: string
    time_descriptor?: string
    user_identity?: string
    enable_thinking?: boolean
  },
  h: StreamHandlers,
): () => void {
  return runSSE(`${BASE}/review/${kbId}/generate`, params, h)
}

/** 模块七：课后追问（已有会话内）。 */
export function streamReviewFollowup(
  kbId: string,
  conversationId: string,
  content: string,
  h: StreamHandlers,
): () => void {
  return runSSE(`${BASE}/review/${kbId}/followup`, { conversation_id: conversationId, content }, h)
}

/** 模块九：课程信息问答（conversationId 为空时后端自动建会话）。 */
export function streamCourseInfoChat(
  kbId: string,
  content: string,
  conversationId: string | null,
  h: StreamHandlers & { enableThinking?: boolean },
): () => void {
  const { enableThinking, ...rest } = h
  return runSSE(`${BASE}/course-info/${kbId}/chat`, {
    content,
    conversation_id: conversationId,
    enable_thinking: enableThinking ?? false,
  }, rest)
}

// ── 文件夹同步 ─────────────────────────────────────────────

export async function syncFolder(kbId: string): Promise<SyncDiff> {
  const res = await fetch(`${BASE}/kb/${kbId}/sync-folder`, { method: "POST" })
  return handleResponse<SyncDiff>(res)
}

// ── 多轮对话 CRUD ──────────────────────────────────────────

export async function createConversation(
  kbId: string,
  scenario: string,
  title = "",
  metadata: Record<string, unknown> = {},
  enableThinking = false,
): Promise<ConversationInfo> {
  const res = await fetch(`${BASE}/conversations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kb_id: kbId, scenario, title, metadata, enable_thinking: enableThinking }),
  })
  return handleResponse<ConversationInfo>(res)
}

export async function getConversation(convId: string): Promise<ConversationInfo> {
  const res = await fetch(`${BASE}/conversations/${convId}`)
  return handleResponse<ConversationInfo>(res)
}

export async function listConversations(kbId: string, scenario?: string): Promise<ConversationInfo[]> {
  const url = scenario
    ? `${BASE}/conversations?kb_id=${kbId}&scenario=${scenario}`
    : `${BASE}/conversations?kb_id=${kbId}`
  const res = await fetch(url)
  return handleResponse<ConversationInfo[]>(res)
}

export async function updateConversation(
  convId: string,
  fields: { title?: string; enable_thinking?: boolean },
): Promise<ConversationInfo> {
  const res = await fetch(`${BASE}/conversations/${convId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  })
  return handleResponse<ConversationInfo>(res)
}

export async function deleteConversation(convId: string, cascade = false): Promise<void> {
  const res = await fetch(`${BASE}/conversations/${convId}?cascade=${cascade}`, { method: "DELETE" })
  await handleResponse<unknown>(res)
}

export async function forkConversation(
  convId: string,
  forkAfterMessageId: string,
  newTitle = "",
): Promise<ConversationInfo> {
  const res = await fetch(`${BASE}/conversations/${convId}/fork`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fork_after_message_id: forkAfterMessageId, new_title: newTitle }),
  })
  return handleResponse<ConversationInfo>(res)
}

// ── 课程管家 REST ──────────────────────────────────────────

export async function generateCourseInfoCard(kbId: string): Promise<CourseInfoCard> {
  const res = await fetch(`${BASE}/course-info/${kbId}/generate`, { method: "POST" })
  return handleResponse<CourseInfoCard>(res)
}

export async function getCourseInfoCard(kbId: string): Promise<CourseInfoCard> {
  const res = await fetch(`${BASE}/course-info/${kbId}`)
  return handleResponse<CourseInfoCard>(res)
}

export async function getUpcomingDeadlines(kbId: string, withinDays = 7): Promise<DeadlineItem[]> {
  const res = await fetch(`${BASE}/course-info/${kbId}/upcoming-deadlines?within_days=${withinDays}`)
  const data = await handleResponse<{ deadlines: DeadlineItem[] }>(res)
  return data.deadlines
}

export async function deleteCourseInfoCard(kbId: string): Promise<void> {
  const res = await fetch(`${BASE}/course-info/${kbId}`, { method: "DELETE" })
  await handleResponse<unknown>(res)
}

// ── 课后复习 REST ──────────────────────────────────────────

export async function listReviewDates(kbId: string): Promise<ReviewDateInfo[]> {
  const res = await fetch(`${BASE}/review/${kbId}/dates`)
  const data = await handleResponse<{ dates: ReviewDateInfo[] }>(res)
  return data.dates
}

export async function listReviewSections(kbId: string, date: string): Promise<ReviewSectionInfo[]> {
  const res = await fetch(`${BASE}/review/${kbId}/sections?date=${date}`)
  const data = await handleResponse<{ sections: ReviewSectionInfo[] }>(res)
  return data.sections
}

export async function saveReviewNotes(kbId: string, conversationId: string): Promise<unknown> {
  const res = await fetch(`${BASE}/review/${kbId}/save-notes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conversation_id: conversationId }),
  })
  return handleResponse<unknown>(res)
}

export async function loadReviewNotes(kbId: string, date: string): Promise<ReviewNote[]> {
  const res = await fetch(`${BASE}/review/${kbId}/notes?date=${encodeURIComponent(date)}`)
  const data = await handleResponse<{ notes: ReviewNote[] }>(res)
  return data.notes
}

export async function listReviewConversations(kbId: string): Promise<ConversationInfo[]> {
  const res = await fetch(`${BASE}/review/${kbId}/conversations`)
  const data = await handleResponse<{ conversations: ConversationInfo[] }>(res)
  return data.conversations
}

// ── 提示词管理 ─────────────────────────────────────────────

export async function listPrompts(): Promise<Record<string, string>> {
  const data = await handleResponse<{ prompts: Record<string, string> }>(
    await fetch(`${BASE}/settings/prompts`)
  )
  return data.prompts
}

export async function reloadPrompts(): Promise<{ detail: string; count: number }> {
  return handleResponse(await fetch(`${BASE}/settings/prompts/reload`, { method: "POST" }))
}
