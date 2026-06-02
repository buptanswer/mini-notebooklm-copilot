import { useEffect, useRef, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { motion } from "motion/react"
import { History, MessagesSquare, Plus, ScanSearch, Sparkles, X } from "lucide-react"
import { Document, Page, pdfjs } from "react-pdf"
import {
  createConversation, forkConversation, getConversation, getOriginPdfUrl,
  listConversations, streamSend,
} from "@/api/client"
import type { CitationItem, ConversationInfo } from "@/api/types"
import { threadFromHistory, useConversation } from "@/hooks/useConversation"
import { ChatThread, Composer } from "@/components/ChatThread"
import { Dialog, DialogClose, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { cn } from "@/lib/utils"

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString()

interface PreviewState { url: string; pageNumber: number; bboxes: number[][]; title: string }

const toUserPage = (z?: number) => Math.max(1, (z ?? 0) + 1)
const normalizeBBoxes = (boxes?: number[][]): number[][] =>
  (boxes ?? [])
    .filter((b) => Array.isArray(b) && b.length >= 4)
    .map((b) => b.slice(0, 4).map((v) => Math.max(0, Math.min(1000, Number(v) || 0))))
    .filter((b) => b[2] > b[0] && b[3] > b[1])

export default function ChatPage() {
  const { kbId, conversationId: urlConvId } = useParams<{ kbId: string; conversationId?: string }>()
  const navigate = useNavigate()
  const convo = useConversation()
  const [enableThinking, setEnableThinking] = useState(false)
  const [history, setHistory] = useState<ConversationInfo[]>([])
  const [showHistory, setShowHistory] = useState(false)
  const [preview, setPreview] = useState<PreviewState | null>(null)
  const [pdfWidth, setPdfWidth] = useState(820)
  const scrollRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onResize = () => setPdfWidth(Math.max(360, Math.min(1000, window.innerWidth - 320)))
    onResize()
    window.addEventListener("resize", onResize)
    return () => window.removeEventListener("resize", onResize)
  }, [])

  useEffect(() => {
    if (!kbId) return
    listConversations(kbId, "chat").then(setHistory).catch(() => {})
  }, [kbId, convo.convId])

  useEffect(() => {
    if (!kbId) return
    if (!urlConvId) { convo.reset([], null); return }
    getConversation(urlConvId)
      .then((c) => convo.reset(threadFromHistory(c.messages || []), urlConvId))
      .catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId, urlConvId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [convo.messages])

  const send = async (text: string) => {
    if (!kbId) return
    let cid = convo.convId
    if (!cid) {
      try {
        const c = await createConversation(kbId, "chat", "", {}, enableThinking)
        cid = c.conversation_id
        convo.setConvId(cid)
      } catch (e) {
        alert("创建会话失败：" + (e as Error).message)
        return
      }
    }
    const id = cid
    convo.start({
      optimisticUser: text,
      starter: (h) => streamSend(id, text, { ragMode: true, topK: 5, enableThinking, ...h }),
    })
  }

  const handleFork = async (messageId: string) => {
    if (!convo.convId || !kbId) return
    try {
      const forked = await forkConversation(convo.convId, messageId, "")
      navigate(`/kb/${kbId}/chat/${forked.conversation_id}`)
    } catch (e) {
      alert("分叉失败：" + (e as Error).message)
    }
  }

  const openPreview = (c: CitationItem) => {
    if (!kbId) return
    setPreview({
      url: getOriginPdfUrl(kbId, c.doc_id),
      pageNumber: toUserPage(c.page_span_start),
      bboxes: normalizeBBoxes(c.bbox_norm1000),
      title: c.header_path?.length ? c.header_path.join(" › ") : c.doc_id,
    })
  }

  // 演示打通：从来源跳「解析透视」并定位到该来源块；从对话跳「检索透视」透视本次检索
  const openDissect = (c: CitationItem) => {
    if (!kbId) return
    navigate(`/kb/${kbId}/dissect?doc=${c.doc_id}&child=${encodeURIComponent(c.child_chunk_id)}`)
  }
  const lastUserQuestion = [...convo.messages].reverse().find((m) => m.role === "user")?.content ?? ""
  const openRetrievalXray = () => {
    if (!kbId || !lastUserQuestion) return
    navigate(`/kb/${kbId}/xray?q=${encodeURIComponent(lastUserQuestion)}`)
  }

  return (
    <div className="flex h-full flex-col">
      {/* 顶栏 */}
      <header className="flex shrink-0 items-center justify-between border-b border-border px-6 py-3">
        <h1 className="flex items-center gap-2 font-display text-lg font-semibold text-ink">
          <MessagesSquare className="h-5 w-5 text-accent" />
          对话问答
        </h1>
        <div className="flex items-center gap-2">
          {lastUserQuestion && (
            <button
              onClick={openRetrievalXray}
              title="把刚才这个问题的检索全过程透视一遍"
              className="flex items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1.5 text-xs font-medium text-ink-soft transition-colors hover:text-accent"
            >
              <ScanSearch className="h-3.5 w-3.5" />
              透视检索
            </button>
          )}
          <button
            onClick={() => { convo.reset([], null); navigate(`/kb/${kbId}/chat`) }}
            className="flex items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1.5 text-xs font-medium text-ink-soft transition-colors hover:text-accent"
          >
            <Plus className="h-3.5 w-3.5" />
            新对话
          </button>
          <button
            onClick={() => setShowHistory((v) => !v)}
            className={cn(
              "flex h-8 w-8 items-center justify-center rounded-full border border-border transition-colors",
              showHistory ? "bg-accent-soft text-accent" : "text-ink-faint hover:text-ink-soft",
            )}
            title="历史对话"
          >
            <History className="h-4 w-4" />
          </button>
        </div>
      </header>

      {/* 历史下拉 */}
      {showHistory && history.length > 0 && (
        <div className="max-h-44 shrink-0 overflow-y-auto border-b border-border bg-surface-2/40 px-6 py-2">
          <div className="mb-1 flex items-center justify-between">
            <span className="text-xs font-medium text-ink-faint">历史对话</span>
            <button onClick={() => setShowHistory(false)}><X className="h-3.5 w-3.5 text-ink-faint" /></button>
          </div>
          {history.map((c) => (
            <button
              key={c.conversation_id}
              onClick={() => { setShowHistory(false); navigate(`/kb/${kbId}/chat/${c.conversation_id}`) }}
              className={cn(
                "mb-0.5 block w-full truncate rounded-lg px-2.5 py-1.5 text-left text-xs transition-colors",
                convo.convId === c.conversation_id ? "bg-accent-soft text-accent" : "text-ink-soft hover:bg-surface-2",
              )}
            >
              {c.title || `对话 ${c.conversation_id.slice(0, 8)}`}
              <span className="ml-2 text-ink-faint">{new Date(c.updated_at).toLocaleDateString()}</span>
            </button>
          ))}
        </div>
      )}

      {/* 线程 */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto">
        <div className="reader-measure mx-auto px-6 py-6">
          <ChatThread
            messages={convo.messages}
            streaming={convo.streaming}
            onToggleThinking={convo.toggleThinking}
            onFork={handleFork}
            onViewSource={openPreview}
            onDissectSource={openDissect}
            emptyState={
              <motion.div
                initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
                className="flex flex-col items-center gap-3 text-center text-ink-faint"
              >
                <Sparkles className="h-10 w-10 text-accent opacity-60" />
                <p className="font-display text-lg text-ink-soft">向知识库提问</p>
                <p className="max-w-xs text-sm">AI 会基于已索引的文档作答，并标注来源。</p>
              </motion.div>
            }
          />
          {convo.error && (
            <div className="mt-4 rounded-xl border border-border bg-accent-soft px-4 py-2.5 text-sm text-accent">
              ⚠ {convo.error}
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* 输入 */}
      <div className="shrink-0 border-t border-border bg-surface/50 px-6 py-3">
        <div className="reader-measure mx-auto">
          <Composer
            onSend={send}
            disabled={convo.streaming}
            placeholder="向知识库提问…（Enter 发送，Shift+Enter 换行）"
            enableThinking={enableThinking}
            onToggleThinking={setEnableThinking}
          />
        </div>
      </div>

      {/* PDF 原文预览 */}
      <Dialog open={!!preview} onClose={() => setPreview(null)} className="w-full max-w-6xl">
        <DialogClose onClick={() => setPreview(null)} />
        <DialogHeader>
          <DialogTitle>原文预览 (p.{preview?.pageNumber ?? 1}){preview?.title ? ` · ${preview.title}` : ""}</DialogTitle>
        </DialogHeader>
        <div className="h-[72vh] overflow-auto rounded-lg bg-surface-2 p-4">
          {preview && (
            <div className="mx-auto w-fit">
              <div className="relative shadow-pop">
                <Document
                  file={preview.url}
                  loading={<div className="p-6 text-sm text-ink-soft">PDF 加载中…</div>}
                  error={<div className="p-6 text-sm text-accent">PDF 加载失败（origin.pdf 可能不存在）</div>}
                >
                  <Page pageNumber={preview.pageNumber} width={pdfWidth} renderAnnotationLayer={false} renderTextLayer={false} />
                </Document>
                {preview.bboxes.map((bbox, idx) => (
                  <div
                    key={`${idx}-${bbox.join("-")}`}
                    className="pointer-events-none absolute border-2 border-accent bg-accent/15"
                    style={{
                      left: `${bbox[0] / 10}%`, top: `${bbox[1] / 10}%`,
                      width: `${(bbox[2] - bbox[0]) / 10}%`, height: `${(bbox[3] - bbox[1]) / 10}%`,
                    }}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      </Dialog>
    </div>
  )
}
