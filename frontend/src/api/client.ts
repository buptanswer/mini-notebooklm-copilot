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

// ── 流式问答（SSE）────────────────────────────────────────

/**
 * 发起 SSE 流式问答，通过回调函数逐事件通知调用者。
 * 返回一个 abort 函数，可中途取消请求。
 */
export function streamChat(
  kbId: string,
  query: string,
  options: {
    topK?: number
    enableThinking?: boolean
    onEvent: (event: ChatEvent) => void
    onError?: (err: Error) => void
    onDone?: () => void
  },
): () => void {
  const controller = new AbortController()
  const { topK = 5, enableThinking = false, onEvent, onError, onDone } = options

  const run = async () => {
    try {
      const res = await fetch(`${BASE}/chat/${kbId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, top_k: topK, enable_thinking: enableThinking }),
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
            const event = JSON.parse(data) as ChatEvent
            onEvent(event)
            if (event.type === "end") {
              onDone?.()
              return
            }
          } catch { /* ignore malformed */ }
        }
      }
      onDone?.()
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        onError?.(err as Error)
      }
    }
  }

  run()
  return () => controller.abort()
}

// ── 文件夹同步 ─────────────────────────────────────────────

export async function syncFolder(kbId: string): Promise<SyncDiff> {
  const res = await fetch(`${BASE}/kb/${kbId}/sync-folder`, { method: "POST" })
  return handleResponse<SyncDiff>(res)
}

// ── 多轮对话 ───────────────────────────────────────────────

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

export function streamConversation(
  convId: string,
  content: string,
  options: {
    metadata?: Record<string, unknown>
    extraSystem?: string
    onEvent: (event: ChatEvent & { section_num?: number }) => void
    onError?: (err: Error) => void
    onDone?: () => void
  },
): () => void {
  const controller = new AbortController()
  const { metadata, extraSystem, onEvent, onError, onDone } = options

  const run = async () => {
    try {
      const res = await fetch(`${BASE}/conversations/${convId}/send`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, metadata: metadata || {}, extra_system: extraSystem }),
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
            const event = JSON.parse(data)
            onEvent(event)
            if (event.type === "end") { onDone?.(); return }
          } catch { /* ignore */ }
        }
      }
      onDone?.()
    } catch (err) {
      if ((err as Error).name !== "AbortError") onError?.(err as Error)
    }
  }
  run()
  return () => controller.abort()
}

// ── 课程管家 ───────────────────────────────────────────────

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

export function streamCourseInfoChat(
  kbId: string,
  content: string,
  conversationId: string | null,
  options: {
    onEvent: (event: ChatEvent) => void
    onError?: (err: Error) => void
    onDone?: (convId: string) => void
  },
): () => void {
  const controller = new AbortController()
  const { onEvent, onError, onDone } = options

  const run = async () => {
    try {
      const res = await fetch(`${BASE}/course-info/${kbId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, conversation_id: conversationId }),
        signal: controller.signal,
      })
      if (!res.ok) {
        let detail = `HTTP ${res.status}`
        try { detail = (await res.json()).detail || detail } catch { /* ignore */ }
        throw new Error(detail)
      }
      const newConvId = res.headers.get("X-Conversation-Id") || conversationId || ""
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
            const event = JSON.parse(data) as ChatEvent
            onEvent(event)
            if (event.type === "end") { onDone?.(newConvId); return }
          } catch { /* ignore */ }
        }
      }
      onDone?.(newConvId)
    } catch (err) {
      if ((err as Error).name !== "AbortError") onError?.(err as Error)
    }
  }
  run()
  return () => controller.abort()
}

// ── 课后复习 ───────────────────────────────────────────────

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

export function streamReviewGenerate(
  kbId: string,
  params: {
    date: string
    course_name?: string
    time_descriptor?: string
    user_identity?: string
    enable_thinking?: boolean
  },
  options: {
    onEvent: (event: Record<string, unknown>) => void
    onError?: (err: Error) => void
    onDone?: () => void
  },
): () => void {
  const controller = new AbortController()
  const { onEvent, onError, onDone } = options

  const run = async () => {
    try {
      const res = await fetch(`${BASE}/review/${kbId}/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
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
            const event = JSON.parse(data) as Record<string, unknown>
            onEvent(event)
            if (event.type === "all_done") { onDone?.(); return }
          } catch { /* ignore */ }
        }
      }
      onDone?.()
    } catch (err) {
      if ((err as Error).name !== "AbortError") onError?.(err as Error)
    }
  }
  run()
  return () => controller.abort()
}

export function streamReviewFollowup(
  kbId: string,
  conversationId: string,
  content: string,
  options: {
    onEvent: (event: ChatEvent) => void
    onError?: (err: Error) => void
    onDone?: () => void
  },
): () => void {
  const controller = new AbortController()
  const { onEvent, onError, onDone } = options

  const run = async () => {
    try {
      const res = await fetch(`${BASE}/review/${kbId}/followup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ conversation_id: conversationId, content }),
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
            const event = JSON.parse(data) as ChatEvent
            onEvent(event)
            if (event.type === "end") { onDone?.(); return }
          } catch { /* ignore */ }
        }
      }
      onDone?.()
    } catch (err) {
      if ((err as Error).name !== "AbortError") onError?.(err as Error)
    }
  }
  run()
  return () => controller.abort()
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
