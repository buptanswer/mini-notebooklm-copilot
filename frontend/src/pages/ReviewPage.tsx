import { useEffect, useRef, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import { motion } from "motion/react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import {
  Brain, CalendarDays, CheckCircle2, FileText, Play, Printer, RefreshCw, Save, Sparkles,
} from "lucide-react"
import {
  forkConversation, getConversation, listReviewConversations, listReviewDates,
  listReviewSections, loadReviewNotes, saveReviewNotes, streamReviewFollowup, streamReviewGenerate,
  exportReviewNotes,
} from "@/api/client"
import type { CitationItem, ConversationInfo, ReviewDateInfo, ReviewSectionInfo } from "@/api/types"
import { threadFromHistory, useConversation, type ThreadMessage } from "@/hooks/useConversation"
import { streamSignature, useStickToBottom } from "@/hooks/useStickToBottom"
import { ChatThread, Composer } from "@/components/ChatThread"
import { usePdfPreview } from "@/components/SourcePreview"
import { cn } from "@/lib/utils"

export default function ReviewPage() {
  const { kbId, conversationId: urlConvId } = useParams<{ kbId: string; conversationId?: string }>()
  const navigate = useNavigate()
  const convo = useConversation()
  const scrollRef = useRef<HTMLDivElement>(null)
  const { openPreview, previewNode } = usePdfPreview(kbId)
  useStickToBottom(scrollRef, streamSignature(convo.messages))

  const openDissect = (c: CitationItem) => {
    if (!kbId) return
    navigate(`/kb/${kbId}/dissect?doc=${c.doc_id}&child=${encodeURIComponent(c.child_chunk_id)}`)
  }

  const [dates, setDates] = useState<ReviewDateInfo[]>([])
  const [selectedDate, setSelectedDate] = useState("")
  const [sections, setSections] = useState<ReviewSectionInfo[]>([])
  const [history, setHistory] = useState<ConversationInfo[]>([])

  const timeDescriptor = ""
  const [userIdentity, setUserIdentity] = useState("北邮通信工程专业大二下")
  const [enableThinking, setEnableThinking] = useState(false)
  const [enableRag, setEnableRag] = useState(false)
  const [savedMsg, setSavedMsg] = useState("")
  const [isGenerating, setIsGenerating] = useState(false)

  const hasSections = convo.messages.some((m) => (m.metadata as { kind?: string }).kind === "section")
  const printSections = convo.messages.filter(
    (m) => m.role === "assistant" && (m.metadata as { kind?: string }).kind === "section",
  )
  const sectionsDone = hasSections && !convo.streaming
  const readOnly = !convo.convId // 磁盘只读视图（无会话）
  const hasFollowup = convo.messages.some(
    (m) => m.role === "user" || (m.role === "assistant" && (m.metadata as { kind?: string }).kind !== "section")
  )

  const refreshDates = () => { if (kbId) listReviewDates(kbId).then(setDates).catch(() => {}) }

  useEffect(() => { refreshDates() /* eslint-disable-next-line */ }, [kbId])
  useEffect(() => {
    if (kbId) listReviewConversations(kbId).then(setHistory).catch(() => {})
  }, [kbId, convo.convId])
  useEffect(() => {
    if (kbId && selectedDate) listReviewSections(kbId, selectedDate).then(setSections).catch(() => {})
  }, [kbId, selectedDate])

  useEffect(() => {
    if (!convo.streaming && selectedDate) {
      refreshDates()
      if (kbId) listReviewSections(kbId, selectedDate).then(setSections).catch(() => {})
      if (isGenerating) {
        setIsGenerating(false)
        setSavedMsg("讲义已自动保存到磁盘，并已索引供问答检索")
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [convo.streaming])

  // 打开历史会话：线程化重载（修复重载错乱）
  useEffect(() => {
    if (!kbId || !urlConvId) return
    setSavedMsg("")
    getConversation(urlConvId)
      .then((c) => {
        const date = (c.metadata as { date?: string })?.date || ""
        setSelectedDate(date)
        convo.reset(threadFromHistory(c.messages || []), urlConvId)
      })
      .catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId, urlConvId])

  const selectDate = (d: string) => {
    setSelectedDate(d)
    setSavedMsg("")
    convo.reset([], null)
    if (urlConvId) navigate(`/kb/${kbId}/review`)
  }

  const handleGenerate = () => {
    if (!kbId || !selectedDate || convo.streaming) return
    setSavedMsg("")
    setIsGenerating(true)
    convo.reset([], null)
    convo.start({
      starter: (h) => streamReviewGenerate(
        kbId,
        { date: selectedDate, time_descriptor: timeDescriptor, user_identity: userIdentity, enable_thinking: enableThinking },
        h,
      ),
    })
  }

  const handleFollowup = (text: string) => {
    if (!kbId) return
    convo.start({
      optimisticUser: text,
      starter: (h) => streamReviewFollowup(kbId, convo.convId, text, {
        enableThinking,
        enableRag,
        date: selectedDate,
        ...h
      }),
    })
  }

  const handleFork = async (messageId: string) => {
    if (!kbId || !convo.convId) return
    try {
      const forked = await forkConversation(convo.convId, messageId, "")
      navigate(`/kb/${kbId}/review/${forked.conversation_id}`)
    } catch (e) {
      alert("分叉失败：" + (e as Error).message)
    }
  }

  const handleSave = async () => {
    if (!kbId || !convo.convId) return
    try {
      await saveReviewNotes(kbId, convo.convId)
      setSavedMsg("讲义已保存到磁盘，并已索引供问答检索")
      refreshDates()
    } catch (e) {
      setSavedMsg("保存失败：" + (e as Error).message)
    }
  }

  const viewSaved = async () => {
    if (!kbId) return
    const notes = await loadReviewNotes(kbId, selectedDate).catch(() => [])
    if (!notes.length) return
    const thread: ThreadMessage[] = notes.map((n) => ({
      id: `disk-${n.section_num}`, role: "assistant", content: n.content_md, thinking: "", agentSteps: [],
      citations: [], metadata: { kind: "section", section_num: n.section_num }, streaming: false, showThinking: false,
    }))
    convo.reset(thread, null)
    setSavedMsg("已加载磁盘讲义（只读）")
  }

  // 导出 PDF：走浏览器「打印 → 另存为 PDF」（客户端，无需 pandoc/LaTeX 引擎，中文排版完美）。
  // 导出 MD：后端直接下载 Markdown 原文。
  const handleExport = async (format: "pdf" | "md") => {
    if (!kbId) return
    if (format === "pdf") {
      if (printSections.length === 0) { setSavedMsg("没有可导出的讲义内容"); return }
      setSavedMsg("已打开打印对话框：在「目标」中选择「另存为 PDF」即可导出带中文排版的 PDF。")
      setTimeout(() => window.print(), 60)
      return
    }
    try {
      setSavedMsg("正在导出 Markdown...")
      const blob = await exportReviewNotes(kbId, {
        conversationId: convo.convId,
        date: selectedDate,
        format,
      })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `${selectedDate}_课堂讲义.${format}`
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(url)
      setSavedMsg("讲义 Markdown 导出成功！")
    } catch (e) {
      const msg = (e as Error).message
      setSavedMsg("导出失败：" + msg)
      alert("讲义 Markdown 导出失败！\n" + msg)
    }
  }

  return (
    <div className="flex h-full">
      {/* 左：日期 + 历史 */}
      <aside className="flex w-56 shrink-0 flex-col overflow-y-auto border-r border-border bg-surface/40 p-3">
        <div className="mb-2 flex items-center justify-between px-1">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-ink-faint">课堂日期</h2>
          <button onClick={refreshDates} className="text-ink-faint hover:text-accent">
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
        </div>
        {dates.length === 0 && (
          <p className="px-1 py-4 text-center text-xs text-ink-faint">暂无录音，请先绑定文件夹并同步</p>
        )}
        {dates.map((d) => (
          <button
            key={d.date}
            onClick={() => selectDate(d.date)}
            className={cn(
              "mb-1 w-full rounded-xl px-3 py-2 text-left text-sm transition-all",
              selectedDate === d.date && !urlConvId ? "bg-accent-soft text-accent" : "text-ink-soft hover:bg-surface-2",
            )}
          >
            <div className="flex items-center justify-between">
              <span className="font-medium">{d.date}</span>
              {d.has_notes && <CheckCircle2 className="h-3.5 w-3.5 text-[color:var(--c-success)]" />}
            </div>
            <div className="mt-0.5 text-xs text-ink-faint">{d.section_count} 节{d.has_notes ? " · 已有讲义" : ""}</div>
          </button>
        ))}

        {history.length > 0 && (
          <div className="mt-4">
            <h2 className="mb-1 px-1 text-xs font-semibold uppercase tracking-wide text-ink-faint">历史会话</h2>
            {history.map((c) => (
              <button
                key={c.conversation_id}
                onClick={() => navigate(`/kb/${kbId}/review/${c.conversation_id}`)}
                className={cn(
                  "mb-0.5 block w-full truncate rounded-lg px-2.5 py-1.5 text-left text-xs transition-colors",
                  urlConvId === c.conversation_id ? "bg-accent-soft text-accent" : "text-ink-soft hover:bg-surface-2",
                )}
              >
                {c.title || c.conversation_id.slice(0, 8)}
              </button>
            ))}
          </div>
        )}
      </aside>

      {/* 右：内容 */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {!selectedDate ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-ink-faint">
            <CalendarDays className="h-12 w-12 opacity-40" />
            <p className="font-display text-lg">从左侧选择一个日期开始课后复习</p>
          </div>
        ) : (
          <>
            {/* 头部 */}
            <header className="flex shrink-0 items-center justify-between border-b border-border px-6 py-3">
              <h1 className="font-display text-lg font-semibold text-ink">{selectedDate} · 课后复盘</h1>
              <div className="flex items-center gap-2">
                {!hasSections && !convo.streaming && dates.find((d) => d.date === selectedDate)?.has_notes && (
                  <button onClick={viewSaved} className="flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs text-ink-soft hover:text-accent">
                    <FileText className="h-3.5 w-3.5" />查看已存讲义
                  </button>
                )}
                {sectionsDone && !readOnly && !hasFollowup && !dates.find((d) => d.date === selectedDate)?.has_notes && (
                  <button onClick={handleSave} className="flex items-center gap-1.5 rounded-full bg-accent px-3 py-1.5 text-xs font-medium text-accent-ink hover:brightness-105">
                    <Save className="h-3.5 w-3.5" />保存讲义
                  </button>
                )}
                {hasSections && (
                  <div className="flex items-center gap-2">
                    <button onClick={() => handleExport("pdf")} className="flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs text-ink-soft hover:text-accent">
                      <Printer className="h-3.5 w-3.5" />导出 PDF
                    </button>
                    <button onClick={() => handleExport("md")} className="flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs text-ink-soft hover:text-accent" title="无需 Pandoc 依赖，直接下载 Markdown 原文">
                      <FileText className="h-3.5 w-3.5" />导出 MD
                    </button>
                  </div>
                )}
              </div>
            </header>

            <div ref={scrollRef} className="flex-1 overflow-y-auto">
              <div className="mx-auto max-w-3xl px-6 py-6">
                {savedMsg && (
                  <div
                    className={cn(
                      "mb-4 rounded-xl border px-4 py-2.5 text-sm transition-all",
                      savedMsg.includes("失败")
                        ? "border-accent/30 bg-accent-soft text-accent"
                        : "border-border bg-surface-2 text-ink-soft"
                    )}
                  >
                    {savedMsg.includes("失败") ? "⚠ " : "✓ "}
                    {savedMsg}
                  </div>
                )}

                {/* 生成参数（未生成且无消息时） */}
                {!hasSections && !convo.streaming && (
                  <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="card mb-6 p-6">
                    <h2 className="mb-4 font-display text-base font-semibold text-ink">生成参数</h2>
                    <div className="space-y-4">
                      <label className="block">
                        <span className="text-xs text-ink-soft">身份描述</span>
                        <input value={userIdentity} onChange={(e) => setUserIdentity(e.target.value)}
                          className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-accent/40" />
                      </label>
                    </div>
                    <label className="mt-4 flex w-fit cursor-pointer items-center gap-2 text-sm text-ink-soft">
                      <input type="checkbox" checked={enableThinking} onChange={(e) => setEnableThinking(e.target.checked)} className="accent-[color:var(--c-accent)]" />
                      <Brain className="h-4 w-4 text-accent" />开启思维链
                    </label>
                    {sections.length > 0 && (
                      <p className="mt-3 text-xs text-ink-faint">共 {sections.length} 节：{sections.map((s) => `第${s.section_num}节`).join("、")}</p>
                    )}
                    <button onClick={handleGenerate} disabled={sections.length === 0}
                      className="mt-5 flex items-center gap-2 rounded-xl bg-accent px-4 py-2.5 text-sm font-medium text-accent-ink transition-all hover:brightness-105 disabled:opacity-40">
                      <Play className="h-4 w-4" />开始生成课后讲义
                    </button>
                  </motion.div>
                )}

                {convo.streaming && !hasSections && (
                  <div className="mb-4 flex items-center gap-2 text-sm text-accent">
                    <Sparkles className="breathe-dot h-4 w-4" />正在准备生成…
                  </div>
                )}

                {/* 讲义 + 追问（统一线程） */}
                <ChatThread
                  messages={convo.messages}
                  streaming={convo.streaming}
                  onToggleThinking={convo.toggleThinking}
                  onFork={readOnly ? undefined : handleFork}
                  onViewSource={openPreview}
                  onDissectSource={openDissect}
                  ragMode={hasSections ? enableRag : false}
                  enableThinking={enableThinking}
                />

                {convo.error && (
                  <div className="mt-4 rounded-xl border border-border bg-accent-soft px-4 py-2.5 text-sm text-accent">⚠ {convo.error}</div>
                )}

                {/* 追问输入（有真实会话且讲义已生成，或只读模式下且有讲义） */}
                {(convo.convId || (readOnly && hasSections)) && sectionsDone && (
                  <div className="mt-6">
                    <p className="mb-2 text-xs font-medium uppercase tracking-wide text-ink-faint">课后追问</p>
                    <Composer
                      onSend={handleFollowup}
                      disabled={convo.streaming}
                      placeholder="在本次课堂上下文内继续提问，或开启检索问答整个知识库…"
                      enableThinking={enableThinking}
                      onToggleThinking={setEnableThinking}
                      enableRag={enableRag}
                      onToggleRag={setEnableRag}
                    />
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </div>

      {/* 打印 / 导出 PDF 容器（屏幕外，仅打印时全宽显示） */}
      {printSections.length > 0 && (
        <div id="review-print">
          <div className="rp-title">{selectedDate} · 课后复习讲义</div>
          <div className="rp-meta">共 {printSections.length} 节 · 由 Mini-NotebookLM 生成</div>
          {printSections.map((m) => (
            <div key={m.id} className="rp-section md-prose">
              <h2>第 {(m.metadata as { section_num?: number }).section_num} 节 · 课堂要点</h2>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
            </div>
          ))}
        </div>
      )}
      {previewNode}
    </div>
  )
}
