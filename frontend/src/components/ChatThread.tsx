import { useRef, useState } from "react"
import { AnimatePresence, motion } from "motion/react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import {
  BookOpenText, Brain, ChevronRight, FileScan, FileText, GitBranch, Loader2, ScanSearch, Send, Sparkles,
} from "lucide-react"
import type { CitationItem } from "@/api/types"
import type { ThreadMessage } from "@/hooks/useConversation"
import { AgentTimeline } from "./AgentTimeline"
import { cn } from "@/lib/utils"

/** 流式等待指示器：仅用于"无 agent 决策、无思维链"的纯撰写等待态。 */
function StreamingIndicator({ label }: { label: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-center gap-2.5 py-1.5"
    >
      <div className="relative flex h-6 w-6 items-center justify-center">
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ repeat: Infinity, duration: 2, ease: "linear" }}
          className="absolute inset-0 rounded-full border-2 border-accent/30 border-t-accent"
        />
        <Sparkles className="h-3 w-3 text-accent" />
      </div>
      <span className="thinking-shimmer text-sm font-medium text-ink-soft">{label}</span>
    </motion.div>
  )
}

function Md({ content, compact }: { content: string; compact?: boolean }) {
  return (
    <div className={cn("md-prose", compact && "md-compact")}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  )
}

function ThinkingPanel({
  msg, onToggle,
}: { msg: ThreadMessage; onToggle: (id: string) => void }) {
  const hasThinking = !!msg.thinking
  // 仅当存在真正的模型思维链（reasoning）时才显示该面板。
  // 检索 Agent 的决策过程走 <AgentTimeline>，不再混入思维链。
  if (!hasThinking) return null
  return (
    <div className="mb-2">
      <button
        onClick={() => onToggle(msg.id)}
        className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface-2 px-2.5 py-1 text-xs text-ink-soft transition-colors hover:text-accent"
      >
        <Brain className="h-3.5 w-3.5" />
        {msg.streaming && !msg.content ? (
          <span className="thinking-shimmer font-medium">正在思考…</span>
        ) : (
          <span>{msg.showThinking ? "收起思维链" : "展开思维链"}</span>
        )}
        {(hasThinking || msg.streaming) && (
          <ChevronRight className={cn("h-3 w-3 transition-transform", msg.showThinking && "rotate-90")} />
        )}
      </button>
      <AnimatePresence initial={false}>
        {msg.showThinking && (hasThinking || msg.streaming) && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <div className="mt-2 whitespace-pre-wrap rounded-md border border-border bg-surface-2/60 p-3 font-mono text-xs leading-relaxed text-ink-soft">
              {msg.thinking || <span className="text-ink-faint">正在初始化检索与分析规划...</span>}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function Citations({
  items, docName, onView, onDissect,
}: {
  items: CitationItem[]
  docName?: (docId: string) => string
  onView?: (c: CitationItem) => void
  onDissect?: (c: CitationItem) => void
}) {
  const [open, setOpen] = useState(false)
  if (!items.length) return null
  return (
    <div className="mt-3 border-t border-border pt-2.5">
      <button
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1.5 text-xs font-medium text-ink-faint transition-colors hover:text-accent"
      >
        <FileText className="h-3.5 w-3.5" />
        {items.length} 条来源
        <ChevronRight className={cn("h-3 w-3 transition-transform", open && "rotate-90")} />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.ul
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22 }}
            className="mt-2 space-y-1.5 overflow-hidden"
          >
            {items.map((c) => (
              <li key={c.child_chunk_id} className="rounded-md border border-border bg-surface-2/50 px-3 py-2 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate font-medium text-ink-soft">
                    [{c.index}] {c.header_path?.length ? c.header_path.join(" › ") : docName?.(c.doc_id) || "片段"}
                  </span>
                  <span className="shrink-0 text-ink-faint">
                    {c.page_span_start >= 0 && c.anchor_origin_pdf_path ? `p.${c.page_span_start + 1}` : ""}
                    <span className="ml-1 rounded bg-accent-soft px-1 py-0.5 text-accent">{c.score.toFixed(2)}</span>
                  </span>
                </div>
                <p className="mt-1 line-clamp-2 text-ink-faint">{c.retrieval_text}</p>
                <div className="mt-1.5 flex items-center gap-3">
                  {onView && c.anchor_origin_pdf_path && (
                    <button onClick={() => onView(c)} className="text-accent hover:underline">查看原文 →</button>
                  )}
                  {onDissect && (
                    <button onClick={() => onDissect(c)} className="inline-flex items-center gap-1 text-ink-faint transition-colors hover:text-accent">
                      <FileScan className="h-3 w-3" />解析透视
                    </button>
                  )}
                </div>
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  )
}

function ForkButton({ id, onFork }: { id: string; onFork: (id: string) => void }) {
  return (
    <button
      onClick={() => onFork(id)}
      title="从此处分叉一个新对话分支"
      className="inline-flex items-center gap-1 text-xs text-ink-faint transition-colors hover:text-accent"
    >
      <GitBranch className="h-3.5 w-3.5" />
      分叉
    </button>
  )
}

export interface ChatThreadProps {
  messages: ThreadMessage[]
  streaming: boolean
  onToggleThinking: (id: string) => void
  onFork?: (messageId: string) => void
  docName?: (docId: string) => string
  onViewSource?: (c: CitationItem) => void
  onDissectSource?: (c: CitationItem) => void
  emptyState?: React.ReactNode
  className?: string
  ragMode?: boolean
  enableThinking?: boolean
}

/** 统一会话线程渲染：讲义 section（reader 卡片）/ 普通问答 / 用户消息，全在一条线程。 */
export function ChatThread({
  messages, streaming, onToggleThinking, onFork, docName, onViewSource, onDissectSource,
  emptyState, className, ragMode = true, enableThinking = false,
}: ChatThreadProps) {
  const endRef = useRef<HTMLDivElement>(null)

  if (messages.length === 0 && emptyState) {
    return <div className={cn("flex h-full items-center justify-center", className)}>{emptyState}</div>
  }

  return (
    <div className={cn("space-y-5", className)}>
      <AnimatePresence initial={false}>
        {messages.map((m) => {
          const isSection = m.role === "assistant" && (m.metadata as { kind?: string }).kind === "section"
          const sectionNum = (m.metadata as { section_num?: number }).section_num
          // 是否展示「多轮检索 Agent 决策透视」：已有决策步骤，或 rag 路刚开始流式（先占位初始化态）
          const showAgent = m.agentSteps.length > 0 || (ragMode && m.streaming && !m.content)

          if (m.role === "user") {
            return (
              <motion.div
                key={m.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
                className="flex justify-end"
              >
                <div className="max-w-[82%] rounded-2xl rounded-br-md bg-accent px-4 py-2.5 font-sans text-[15px] leading-relaxed text-accent-ink shadow-card">
                  {m.content}
                </div>
              </motion.div>
            )
          }

          // assistant — section（讲义）或普通回答
          return (
            <motion.div
              key={m.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
              className={cn(isSection ? "card overflow-hidden" : "max-w-[92%]")}
            >
              {isSection && (
                <div className="flex items-center justify-between border-b border-border bg-surface-2/50 px-5 py-3">
                  <span className="flex items-center gap-2 font-display text-base font-semibold text-ink">
                    <BookOpenText className="h-4 w-4 text-accent" />
                    第 {sectionNum} 节 · 课堂要点
                  </span>
                  <span className="flex items-center gap-3">
                    {m.streaming
                      ? <span className="flex items-center gap-1 text-xs text-accent"><Loader2 className="h-3 w-3 animate-spin" />生成中</span>
                      : <span className="text-xs text-ink-faint">已生成</span>}
                    {!m.streaming && onFork && <ForkButton id={m.id} onFork={onFork} />}
                  </span>
                </div>
              )}

              <div className={cn(isSection ? "px-5 py-4" : "")}>
                {showAgent && (
                  <div className="mb-3">
                    <AgentTimeline steps={m.agentSteps} active={m.streaming && !m.content} variant="inline" />
                  </div>
                )}

                <ThinkingPanel msg={m} onToggle={onToggleThinking} />

                {m.content ? (
                  <div className={m.streaming ? "stream-caret" : ""}>
                    <Md content={m.content} compact={!isSection} />
                  </div>
                ) : m.streaming && !showAgent && !m.thinking ? (
                  <StreamingIndicator label={enableThinking ? "正在深度思考…" : "正在撰写回答…"} />
                ) : null}

                <Citations items={m.citations} docName={docName} onView={onViewSource} onDissect={onDissectSource} />

                {!isSection && !m.streaming && onFork && (
                  <div className="mt-2.5 flex items-center gap-3">
                    <ForkButton id={m.id} onFork={onFork} />
                  </div>
                )}
              </div>
            </motion.div>
          )
        })}
      </AnimatePresence>
      {streaming && messages.length > 0 && <div ref={endRef} />}
    </div>
  )
}

// ── 输入器 ─────────────────────────────────────────────────

export interface ComposerProps {
  onSend: (text: string) => void
  disabled?: boolean
  placeholder?: string
  enableThinking?: boolean
  onToggleThinking?: (v: boolean) => void
  enableRag?: boolean
  onToggleRag?: (v: boolean) => void
  autoFocus?: boolean
}

export function Composer({
  onSend, disabled, placeholder = "继续提问…", enableThinking, onToggleThinking,
  enableRag, onToggleRag, autoFocus,
}: ComposerProps) {
  const [text, setText] = useState("")
  const submit = () => {
    const q = text.trim()
    if (!q || disabled) return
    setText("")
    onSend(q)
  }
  const hasToolbar = !!onToggleThinking || !!onToggleRag
  return (
    <div className="rounded-2xl border border-border bg-surface p-2 shadow-card focus-within:border-accent/50 focus-within:ring-2 focus-within:ring-accent/15 transition-colors">
      {/* 第一行：输入框占满整行 + 发送 */}
      <div className="flex items-end gap-2">
        <textarea
          autoFocus={autoFocus}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit() }
          }}
          rows={1}
          placeholder={placeholder}
          className="max-h-40 min-h-[2.5rem] flex-1 resize-none bg-transparent px-2 py-2 font-sans text-[15px] leading-relaxed text-ink placeholder:text-ink-faint focus:outline-none"
        />
        <button
          onClick={submit}
          disabled={disabled || !text.trim()}
          title="发送"
          className="flex h-9 w-9 shrink-0 items-center justify-center self-end rounded-xl bg-accent text-accent-ink transition-all hover:brightness-105 disabled:opacity-40"
        >
          {disabled ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
        </button>
      </div>

      {/* 第二行：开关工具条（独立成行，不再挤压输入框） */}
      {hasToolbar && (
        <div className="mt-1.5 flex items-center gap-1.5 px-1">
          {onToggleThinking && (
            <button
              onClick={() => onToggleThinking(!enableThinking)}
              title="深度思考：让模型先输出推理思维链，再作答（仅支持的模型生效）"
              className={cn(
                "inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium transition-colors",
                enableThinking
                  ? "border-accent/40 bg-accent-soft text-accent"
                  : "border-border text-ink-faint hover:text-ink-soft",
              )}
            >
              <Brain className="h-3.5 w-3.5" />深度思考
            </button>
          )}
          {onToggleRag && (
            <button
              onClick={() => onToggleRag(!enableRag)}
              title="知识库检索：作答前先从知识库做多轮混合检索并溯源"
              className={cn(
                "inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium transition-colors",
                enableRag
                  ? "border-accent/40 bg-accent-soft text-accent"
                  : "border-border text-ink-faint hover:text-ink-soft",
              )}
            >
              <ScanSearch className="h-3.5 w-3.5" />知识库检索
            </button>
          )}
          <span className="ml-auto hidden select-none text-[11px] text-ink-faint sm:inline">Enter 发送 · Shift+Enter 换行</span>
        </div>
      )}
    </div>
  )
}
