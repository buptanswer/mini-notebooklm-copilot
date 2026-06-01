import { useEffect, useRef, useState } from "react"
import { useParams } from "react-router-dom"
import { motion } from "motion/react"
import {
  AlertCircle, BarChart3, CalendarClock, ClipboardList, Loader2, Mail,
  MessagesSquare, RefreshCw, Trash2, User,
} from "lucide-react"
import {
  deleteCourseInfoCard, forkConversation, generateCourseInfoCard, getConversation,
  getCourseInfoCard, listConversations, streamCourseInfoChat,
} from "@/api/client"
import type { ConversationInfo, CourseInfoCard } from "@/api/types"
import { threadFromHistory, useConversation } from "@/hooks/useConversation"
import { ChatThread, Composer } from "@/components/ChatThread"
import { cn } from "@/lib/utils"

const pct = (v: number) => (v > 0 ? `${Math.round(v * 100)}%` : "—")

export default function CourseInfoPage() {
  const { kbId } = useParams<{ kbId: string }>()
  const convo = useConversation()
  const [card, setCard] = useState<CourseInfoCard | null>(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState("")
  const [enableThinking, setEnableThinking] = useState(false)
  const [history, setHistory] = useState<ConversationInfo[]>([])
  const bottomRef = useRef<HTMLDivElement>(null)

  const loadCard = async () => {
    if (!kbId) return
    setLoading(true)
    try { setCard(await getCourseInfoCard(kbId)) } catch { setCard(null) } finally { setLoading(false) }
  }
  useEffect(() => { loadCard() /* eslint-disable-next-line */ }, [kbId])
  useEffect(() => {
    if (kbId) listConversations(kbId, "course_info").then(setHistory).catch(() => {})
  }, [kbId, convo.convId])
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }) }, [convo.messages])

  const handleGenerate = async () => {
    if (!kbId) return
    setGenerating(true); setError("")
    try { setCard(await generateCourseInfoCard(kbId)) }
    catch (e) { setError((e as Error).message) }
    finally { setGenerating(false) }
  }

  const handleDelete = async () => {
    if (!kbId || !window.confirm("确认重置课程信息卡片？")) return
    try { await deleteCourseInfoCard(kbId); setCard(null); convo.reset([], null) }
    catch (e) { setError((e as Error).message) }
  }

  const send = (text: string) => {
    if (!kbId) return
    convo.start({
      optimisticUser: text,
      starter: (h) => streamCourseInfoChat(kbId, text, convo.convId, { enableThinking, ...h }),
    })
  }

  const handleFork = async (messageId: string) => {
    if (!kbId || !convo.convId) return
    try {
      const forked = await forkConversation(convo.convId, messageId, "")
      const c = await getConversation(forked.conversation_id)
      convo.reset(threadFromHistory(c.messages || []), forked.conversation_id)
    } catch (e) { alert("分叉失败：" + (e as Error).message) }
  }

  const loadConv = async (convId: string) => {
    if (!convId) { convo.reset([], null); return }
    const c = await getConversation(convId).catch(() => null)
    if (c) convo.reset(threadFromHistory(c.messages || []), convId)
  }

  if (loading) {
    return <div className="flex h-full items-center justify-center text-ink-faint"><Loader2 className="mr-2 h-5 w-5 animate-spin" />加载中…</div>
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-6 py-6">
        <header className="mb-6 flex items-center justify-between">
          <h1 className="flex items-center gap-2 font-display text-2xl font-semibold text-ink">
            <ClipboardList className="h-6 w-6 text-accent" />课程管家
          </h1>
          {card && (
            <div className="flex gap-2">
              <button onClick={handleGenerate} disabled={generating}
                className="flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs text-ink-soft hover:text-accent disabled:opacity-50">
                <RefreshCw className={cn("h-3.5 w-3.5", generating && "animate-spin")} />重新生成
              </button>
              <button onClick={handleDelete}
                className="flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs text-ink-faint hover:text-accent">
                <Trash2 className="h-3.5 w-3.5" />重置
              </button>
            </div>
          )}
        </header>

        {error && <div className="mb-4 rounded-xl border border-border bg-accent-soft px-4 py-2.5 text-sm text-accent">⚠ {error}</div>}

        {!card && !generating && (
          <div className="card flex flex-col items-center border-dashed p-12 text-center">
            <ClipboardList className="mb-3 h-10 w-10 text-ink-faint opacity-50" />
            <p className="mb-1 font-display text-lg text-ink-soft">尚未生成课程信息卡片</p>
            <p className="mb-6 max-w-sm text-sm text-ink-faint">AI 将从本知识库提取课程名称、老师信息、考核方式、截止日期与重要通知。</p>
            <button onClick={handleGenerate} className="rounded-xl bg-accent px-5 py-2.5 text-sm font-medium text-accent-ink hover:brightness-105">生成课程信息卡片</button>
          </div>
        )}

        {generating && (
          <div className="card p-12 text-center">
            <Loader2 className="mx-auto mb-3 h-8 w-8 animate-spin text-accent" />
            <p className="text-ink-soft">AI 正在提取课程信息…（约 10–30 秒）</p>
          </div>
        )}

        {card && (
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
            {/* 基本信息 */}
            <div className="card p-5">
              <h2 className="mb-3 font-display text-lg font-semibold text-ink">{card.course_name || "课程信息"}</h2>
              <div className="space-y-2 text-sm">
                {card.instructor && (
                  <div className="flex items-start gap-2"><User className="mt-0.5 h-4 w-4 shrink-0 text-ink-faint" /><span className="text-ink-soft">任课老师：</span><span className="text-ink">{card.instructor}</span></div>
                )}
                {card.contact && (
                  <div className="flex items-start gap-2"><Mail className="mt-0.5 h-4 w-4 shrink-0 text-ink-faint" /><span className="text-ink-soft">联系方式：</span><span className="whitespace-pre-wrap text-ink">{card.contact}</span></div>
                )}
              </div>
            </div>

            {/* 考核方式 */}
            {card.assessment && (
              <div className="card p-5">
                <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink-soft"><BarChart3 className="h-4 w-4 text-accent" />考核方式</h3>
                <div className="flex gap-3">
                  {[
                    { label: "期末考试", v: card.assessment.exam_ratio },
                    { label: "作业", v: card.assessment.hw_ratio },
                    { label: "出勤", v: card.assessment.attendance_ratio },
                  ].filter((x) => x.v > 0).map((x) => (
                    <div key={x.label} className="flex-1 rounded-xl bg-surface-2 p-3 text-center">
                      <div className="font-display text-2xl font-semibold text-accent">{pct(x.v)}</div>
                      <div className="text-xs text-ink-faint">{x.label}</div>
                    </div>
                  ))}
                </div>
                {card.assessment.description && <p className="mt-3 text-xs text-ink-faint">{card.assessment.description}</p>}
              </div>
            )}

            {/* 截止日期 */}
            {card.deadlines_normalized?.length > 0 && (
              <div className="card p-5">
                <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink-soft"><CalendarClock className="h-4 w-4 text-accent" />截止日期</h3>
                <div className="space-y-2">
                  {card.deadlines_normalized.map((dl, i) => {
                    const soon = dl.days_left != null && dl.days_left <= 3
                    return (
                      <div key={i} className={cn("flex items-center justify-between rounded-xl px-3 py-2 text-sm", soon ? "bg-accent-soft" : "bg-surface-2")}>
                        <div><span className="font-medium text-ink">{dl.name}</span>{dl.date_text && <span className="ml-2 text-xs text-ink-faint">({dl.date_text})</span>}</div>
                        {dl.days_left != null ? (
                          <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium", dl.days_left <= 0 ? "bg-accent text-accent-ink" : soon ? "text-accent" : "text-ink-faint")}>
                            {dl.days_left <= 0 ? "已截止" : dl.days_left === 1 ? "明天" : `${dl.days_left}天后`}
                          </span>
                        ) : <span className="text-xs text-ink-faint">{dl.date || "日期未知"}</span>}
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* 重要通知 */}
            {card.important_notes && (
              <div className="card p-5">
                <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink-soft"><AlertCircle className="h-4 w-4 text-accent" />重要通知</h3>
                <p className="whitespace-pre-wrap text-sm text-ink">{card.important_notes}</p>
              </div>
            )}
          </motion.div>
        )}

        {/* 问答 */}
        {card && (
          <div className="mt-6">
            <div className="mb-2 flex items-center justify-between">
              <p className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-ink-faint">
                <MessagesSquare className="h-3.5 w-3.5" />课程问答
              </p>
              {history.length > 0 && (
                <select
                  className="max-w-[140px] truncate rounded-lg border border-border bg-surface px-2 py-1 text-xs text-ink-soft"
                  value={convo.convId || ""}
                  onChange={(e) => loadConv(e.target.value)}
                >
                  <option value="">新对话</option>
                  {history.map((c) => <option key={c.conversation_id} value={c.conversation_id}>{c.title || c.conversation_id.slice(0, 8)}</option>)}
                </select>
              )}
            </div>

            {convo.messages.length > 0 && (
              <div className="mb-3 max-h-[28rem] overflow-y-auto rounded-2xl border border-border bg-surface/40 p-4">
                <ChatThread messages={convo.messages} streaming={convo.streaming} onToggleThinking={convo.toggleThinking} onFork={convo.convId ? handleFork : undefined} />
                <div ref={bottomRef} />
              </div>
            )}
            {convo.messages.length === 0 && (
              <p className="mb-3 px-1 text-xs text-ink-faint">试着问："作业怎么提交？""期末什么时候考？""老师邮箱是多少？"</p>
            )}
            <Composer onSend={send} disabled={convo.streaming} placeholder="问关于课程的任何问题…" enableThinking={enableThinking} onToggleThinking={setEnableThinking} />
          </div>
        )}
      </div>
    </div>
  )
}
