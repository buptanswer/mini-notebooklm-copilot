// API 客户端函数

import type {
  ChatEvent,
  DocInfo,
  KBInfo,
  SearchResultItem,
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

export async function createKB(name: string, description = ""): Promise<KBInfo> {
  const res = await fetch(`${BASE}/kb`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description }),
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
