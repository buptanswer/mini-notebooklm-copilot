import { useEffect, useRef, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { ArrowLeft, Send, BookOpen, ChevronDown, ChevronUp, FileText } from "lucide-react"
import { Document, Page, pdfjs } from "react-pdf"
import { streamChat, getOriginPdfUrl } from "@/api/client"
import type { CitationItem } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Spinner } from "@/components/ui/spinner"
import { Badge } from "@/components/ui/badge"
import { Dialog, DialogHeader, DialogTitle, DialogClose } from "@/components/ui/dialog"
import { Separator } from "@/components/ui/separator"

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString()

interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  thinking?: string
  citations?: CitationItem[]
  isStreaming?: boolean
}

interface PreviewState {
  url: string
  pageNumber: number
  bboxes: number[][]
  title: string
}

const toUserPage = (zeroBased?: number) => Math.max(1, (zeroBased ?? 0) + 1)

const normalizeBBoxes = (boxes: number[][] | undefined): number[][] => {
  if (!boxes || boxes.length === 0) return []
  return boxes
    .filter(b => Array.isArray(b) && b.length >= 4)
    .map(b => [
      Math.max(0, Math.min(1000, Number(b[0]) || 0)),
      Math.max(0, Math.min(1000, Number(b[1]) || 0)),
      Math.max(0, Math.min(1000, Number(b[2]) || 0)),
      Math.max(0, Math.min(1000, Number(b[3]) || 0)),
    ])
    .filter(b => b[2] > b[0] && b[3] > b[1])
}

const CitationCard = ({
  item,
  onPreview,
}: {
  item: CitationItem
  onPreview: (item: CitationItem) => void
}) => {
  const [open, setOpen] = useState(false)
  const startPage = toUserPage(item.page_span_start)
  const endPage = toUserPage(item.page_span_end)
  const hasBBox = (item.bbox_norm1000?.length ?? 0) > 0

  return (
    <div className="rounded-lg border border-gray-100 bg-white shadow-sm text-sm">
      <div
        className="flex items-center justify-between px-3 py-2 cursor-pointer hover:bg-gray-50 rounded-lg"
        onClick={() => setOpen(v => !v)}
      >
        <div className="flex items-center gap-2 min-w-0">
          <Badge variant="outline" className="shrink-0 text-xs px-1.5">
            [{item.index}]
          </Badge>
          <span className="text-gray-600 truncate text-xs">
            {item.header_path.length > 0 ? item.header_path.join(" › ") : item.doc_id}
          </span>
          {item.page_span_start != null && (
            <span className="text-gray-400 text-xs shrink-0">
              p.{startPage}
              {item.page_span_end != null && item.page_span_end !== item.page_span_start
                ? `-${endPage}`
                : ""}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <span className="text-gray-300 text-xs">{(item.score * 100).toFixed(0)}%</span>
          {open ? <ChevronUp className="h-3.5 w-3.5 text-gray-400" /> : <ChevronDown className="h-3.5 w-3.5 text-gray-400" />}
        </div>
      </div>
      {open && (
        <div className="px-3 pb-3 space-y-2">
          <Separator />
          <p className="text-xs text-gray-500 leading-relaxed line-clamp-6">{item.retrieval_text}</p>
          {hasBBox && <p className="text-[11px] text-amber-600">支持 bbox 高亮定位</p>}
          <Button
            size="sm"
            variant="outline"
            className="text-xs h-7"
            onClick={() => onPreview(item)}
          >
            <FileText className="h-3 w-3 mr-1" />
            查看原文 (p.{startPage})
          </Button>
        </div>
      )}
    </div>
  )
}

export default function ChatPage() {
  const { kbId } = useParams<{ kbId: string }>()
  const navigate = useNavigate()
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [streaming, setStreaming] = useState(false)
  const [preview, setPreview] = useState<PreviewState | null>(null)
  const [pdfRenderWidth, setPdfRenderWidth] = useState(860)
  const abortRef = useRef<(() => void) | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  useEffect(() => {
    const onResize = () => {
      const next = Math.max(360, Math.min(1000, window.innerWidth - 260))
      setPdfRenderWidth(next)
    }
    onResize()
    window.addEventListener("resize", onResize)
    return () => window.removeEventListener("resize", onResize)
  }, [])

  useEffect(() => {
    return () => {
      abortRef.current?.()
    }
  }, [])

  const send = async () => {
    const q = input.trim()
    if (!q || streaming || !kbId) return
    setInput("")

    const userMsg: Message = { id: Date.now().toString(), role: "user", content: q }
    const assistantId = (Date.now() + 1).toString()
    const assistantMsg: Message = {
      id: assistantId,
      role: "assistant",
      content: "",
      citations: [],
      isStreaming: true,
    }
    setMessages(prev => [...prev, userMsg, assistantMsg])
    setStreaming(true)

    abortRef.current = streamChat(kbId, q, {
      onEvent: (ev) => {
        if (ev.type === "citations") {
          setMessages(prev =>
            prev.map(m => m.id === assistantId ? { ...m, citations: ev.citations } : m)
          )
        } else if (ev.type === "delta") {
          setMessages(prev =>
            prev.map(m =>
              m.id === assistantId ? { ...m, content: m.content + ev.content } : m
            )
          )
        } else if (ev.type === "thinking") {
          setMessages(prev =>
            prev.map(m =>
              m.id === assistantId ? { ...m, thinking: (m.thinking || "") + ev.content } : m
            )
          )
        } else if (ev.type === "end") {
          setMessages(prev =>
            prev.map(m => m.id === assistantId ? { ...m, isStreaming: false } : m)
          )
          setStreaming(false)
        } else if (ev.type === "error") {
          setMessages(prev =>
            prev.map(m =>
              m.id === assistantId
                ? { ...m, content: `⚠ 错误：${ev.message}`, isStreaming: false }
                : m
            )
          )
          setStreaming(false)
        }
      },
      onError: (err) => {
        setMessages(prev =>
          prev.map(m =>
            m.id === assistantId
              ? { ...m, content: `⚠ 连接错误：${err}`, isStreaming: false }
              : m
          )
        )
        setStreaming(false)
      },
      onDone: () => {
        setMessages(prev =>
          prev.map(m => m.id === assistantId ? { ...m, isStreaming: false } : m)
        )
        setStreaming(false)
      },
    })
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  const citations = [...messages].reverse().find((m): m is Message => m.role === "assistant")?.citations ?? []

  const openPreview = (item: CitationItem) => {
    if (!kbId) return
    const pageNumber = toUserPage(item.page_span_start)
    const bboxes = normalizeBBoxes(item.bbox_norm1000)
    const path = item.header_path.length > 0 ? item.header_path.join(" › ") : item.doc_id
    setPreview({
      url: getOriginPdfUrl(kbId, item.doc_id),
      pageNumber,
      bboxes,
      title: path,
    })
  }

  return (
    <div className="flex h-[calc(100vh-4rem)] overflow-hidden">
      {/* Left: Chat */}
      <div className="flex flex-1 flex-col min-w-0">
        {/* Sub-header */}
        <div className="border-b bg-white px-4 py-2.5 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2">
            <button onClick={() => navigate(`/kb/${kbId}`)} className="text-gray-400 hover:text-gray-600">
              <ArrowLeft className="h-4 w-4" />
            </button>
            <span className="text-sm font-medium text-gray-700">对话问答</span>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full text-gray-300 gap-3">
              <BookOpen className="h-12 w-12 opacity-40" />
              <p className="text-sm">向知识库提问，AI 将根据已索引的文档回答</p>
            </div>
          )}
          {messages.map(msg => (
            <div
              key={msg.id}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm
                  ${msg.role === "user"
                    ? "bg-blue-500 text-white"
                    : "bg-gray-100 text-gray-800 shadow-sm"}`}
              >
                {msg.role === "assistant" ? (
                  <>
                    {msg.thinking && (
                      <details className="mb-2">
                        <summary className="cursor-pointer text-xs text-gray-400 select-none">
                          💭 思考过程
                        </summary>
                        <p className="text-xs text-gray-400 mt-1 italic leading-relaxed">
                          {msg.thinking}
                        </p>
                      </details>
                    )}
                    <div className="prose prose-sm prose-gray max-w-none">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {msg.content || (msg.isStreaming ? "" : "（无内容）")}
                      </ReactMarkdown>
                    </div>
                    {msg.isStreaming && (
                      <span className="inline-block h-3 w-0.5 bg-gray-400 ml-0.5 animate-pulse" />
                    )}
                    {(msg.citations?.length ?? 0) > 0 && !msg.isStreaming && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {msg.citations!.map(c => (
                          <span
                            key={c.index}
                            className="text-xs text-blue-500 cursor-pointer hover:underline"
                            title={c.header_path.join(" › ")}
                          >
                            [{c.index}]
                          </span>
                        ))}
                      </div>
                    )}
                  </>
                ) : (
                  msg.content
                )}
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="border-t bg-white px-4 py-3 shrink-0">
          <div className="flex gap-2 items-end">
            <Textarea
              ref={textareaRef}
              placeholder="向知识库提问… (Enter 发送, Shift+Enter 换行)"
              className="flex-1 resize-none min-h-[48px] max-h-[120px] text-sm"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={streaming}
              rows={1}
            />
            <Button
              size="sm"
              className="h-10 px-3 shrink-0"
              onClick={send}
              disabled={streaming || !input.trim()}
            >
              {streaming ? <Spinner size="sm" /> : <Send className="h-4 w-4" />}
            </Button>
          </div>
        </div>
      </div>

      {/* Right: Citations Panel */}
      {citations.length > 0 && (
        <div className="w-72 border-l bg-gray-50 flex flex-col overflow-hidden shrink-0">
          <div className="px-4 py-3 border-b bg-white shrink-0">
            <p className="text-sm font-medium text-gray-700">
              引用来源 ({citations.length})
            </p>
          </div>
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            {citations.map((c: CitationItem) => (
              <CitationCard
                key={c.index}
                item={c}
                onPreview={openPreview}
              />
            ))}
          </div>
        </div>
      )}

      {/* PDF Preview Dialog */}
      <Dialog open={!!preview} onClose={() => setPreview(null)} className="max-w-6xl w-full">
        <DialogClose onClick={() => setPreview(null)} />
        <DialogHeader>
          <DialogTitle>
            原文预览 (p.{preview?.pageNumber ?? 1})
            {preview?.title ? ` · ${preview.title}` : ""}
          </DialogTitle>
        </DialogHeader>
        <div className="h-[72vh] overflow-auto rounded-lg bg-gray-100 p-4">
          {preview && (
            <div className="mx-auto w-fit">
              <div className="relative shadow-lg">
                <Document
                  file={preview.url}
                  loading={<div className="p-6 text-sm text-gray-500">PDF 加载中...</div>}
                  error={<div className="p-6 text-sm text-red-500">PDF 加载失败，请检查 origin.pdf 是否存在</div>}
                >
                  <Page
                    pageNumber={preview.pageNumber}
                    width={pdfRenderWidth}
                    renderAnnotationLayer={false}
                    renderTextLayer={false}
                  />
                </Document>

                {preview.bboxes.map((bbox, idx) => (
                  <div
                    key={`${idx}-${bbox.join("-")}`}
                    className="pointer-events-none absolute border-2 border-amber-500 bg-amber-300/20 shadow-[0_0_0_1px_rgba(245,158,11,0.4)]"
                    style={{
                      left: `${bbox[0] / 10}%`,
                      top: `${bbox[1] / 10}%`,
                      width: `${(bbox[2] - bbox[0]) / 10}%`,
                      height: `${(bbox[3] - bbox[1]) / 10}%`,
                    }}
                    title="bbox 高亮定位"
                  />
                ))}
              </div>

              {preview.bboxes.length === 0 && (
                <p className="mt-3 text-xs text-gray-500">该引用未提供 bbox 坐标，当前仅定位到页码。</p>
              )}
            </div>
          )}
        </div>
      </Dialog>
    </div>
  )
}
