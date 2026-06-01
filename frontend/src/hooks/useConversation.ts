import { useCallback, useRef, useState } from "react"
import type { ChatEvent, CitationItem, MessageInfo } from "@/api/types"
import type { StreamHandlers } from "@/api/client"

/** 线程中的一条消息（统一模型，供所有场景复用）。 */
export interface ThreadMessage {
  id: string
  role: "user" | "assistant"
  content: string
  thinking: string
  citations: CitationItem[]
  metadata: Record<string, unknown>
  streaming: boolean
  showThinking: boolean
}

function newAssistant(id: string, metadata: Record<string, unknown>): ThreadMessage {
  return { id, role: "assistant", content: "", thinking: "", citations: [], metadata, streaming: true, showThinking: false }
}

/** 把最后一条 assistant 消息（当前流式目标）应用 patch。 */
function patchLastAssistant(
  msgs: ThreadMessage[],
  patch: (m: ThreadMessage) => ThreadMessage,
): ThreadMessage[] {
  for (let i = msgs.length - 1; i >= 0; i--) {
    if (msgs[i].role === "assistant") {
      const copy = [...msgs]
      copy[i] = patch(copy[i])
      return copy
    }
  }
  return msgs
}

/** 从历史消息（含隐藏的讲义生成 prompt）映射为可渲染线程：过滤 hidden user。 */
export function threadFromHistory(msgs: MessageInfo[]): ThreadMessage[] {
  return msgs
    .filter((m) => m.role !== "system" && !(m.role === "user" && (m.metadata as { hidden?: boolean })?.hidden))
    .map((m) => ({
      id: m.message_id,
      role: m.role as "user" | "assistant",
      content: m.content,
      thinking: m.thinking || "",
      citations: m.citations || [],
      metadata: m.metadata || {},
      streaming: false,
      showThinking: false,
    }))
}

export interface UseConversation {
  messages: ThreadMessage[]
  convId: string | null
  streaming: boolean
  error: string
  totalSections: number | null
  setConvId: (id: string | null) => void
  reset: (msgs?: ThreadMessage[], convId?: string | null) => void
  toggleThinking: (id: string) => void
  /** 启动一条流。optimisticUser 非空时先乐观插入一条 user 消息。 */
  start: (opts: { optimisticUser?: string; starter: (h: StreamHandlers) => () => void }) => void
  abort: () => void
}

export function useConversation(initial: ThreadMessage[] = []): UseConversation {
  const [messages, setMessages] = useState<ThreadMessage[]>(initial)
  const [convId, setConvId] = useState<string | null>(null)
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState("")
  const [totalSections, setTotalSections] = useState<number | null>(null)
  const abortRef = useRef<(() => void) | null>(null)

  const abort = useCallback(() => {
    abortRef.current?.()
    abortRef.current = null
    setStreaming(false)
  }, [])

  const reset = useCallback((msgs: ThreadMessage[] = [], cid: string | null = null) => {
    abortRef.current?.()
    abortRef.current = null
    setMessages(msgs)
    setConvId(cid)
    setError("")
    setStreaming(false)
    setTotalSections(null)
  }, [])

  const toggleThinking = useCallback((id: string) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, showThinking: !m.showThinking } : m)))
  }, [])

  const handleEvent = useCallback((ev: ChatEvent) => {
    switch (ev.type) {
      case "conversation":
        setConvId(ev.conversation_id)
        if (typeof ev.total_sections === "number") setTotalSections(ev.total_sections)
        break
      case "message_start":
        if (ev.role === "assistant") {
          setMessages((prev) => [...prev, newAssistant(ev.message_id, ev.metadata ?? {})])
        } else {
          // 协调乐观插入的临时 user 消息 id
          setMessages((prev) => {
            for (let i = prev.length - 1; i >= 0; i--) {
              if (prev[i].role === "user" && prev[i].id.startsWith("tmp-")) {
                const copy = [...prev]
                copy[i] = { ...copy[i], id: ev.message_id }
                return copy
              }
            }
            return prev
          })
        }
        break
      case "citations":
        setMessages((prev) => patchLastAssistant(prev, (m) => ({ ...m, citations: ev.citations })))
        break
      case "thinking":
        setMessages((prev) => patchLastAssistant(prev, (m) => ({ ...m, thinking: m.thinking + ev.content })))
        break
      case "delta":
        setMessages((prev) => patchLastAssistant(prev, (m) => ({ ...m, content: m.content + ev.content })))
        break
      case "message_end":
        setMessages((prev) => prev.map((m) => (m.id === ev.message_id ? { ...m, streaming: false } : m)))
        break
      case "error":
        setError(ev.message)
        break
    }
  }, [])

  const start = useCallback(
    (opts: { optimisticUser?: string; starter: (h: StreamHandlers) => () => void }) => {
      setError("")
      setStreaming(true)
      if (opts.optimisticUser != null) {
        const tmp: ThreadMessage = {
          id: `tmp-${Date.now()}`, role: "user", content: opts.optimisticUser,
          thinking: "", citations: [], metadata: {}, streaming: false, showThinking: false,
        }
        setMessages((prev) => [...prev, tmp])
      }
      abortRef.current = opts.starter({
        onEvent: handleEvent,
        onError: (e) => { setError(e.message); setStreaming(false) },
        onDone: () => setStreaming(false),
      })
    },
    [handleEvent],
  )

  return {
    messages, convId, streaming, error, totalSections,
    setConvId, reset, toggleThinking, start, abort,
  }
}
