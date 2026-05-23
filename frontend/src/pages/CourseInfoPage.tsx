import { useEffect, useRef, useState } from "react"
import { useParams } from "react-router-dom"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import {
  User, Mail, BarChart3, Calendar, AlertCircle, RefreshCw,
  Loader2, Send, MessageSquare, Trash2, Brain, GitBranch,
} from "lucide-react"
import {
  getCourseInfoCard, generateCourseInfoCard, deleteCourseInfoCard,
  streamCourseInfoChat, forkConversation, listConversations, getConversation,
} from "@/api/client"
import type { ChatEvent, ConversationInfo, CourseInfoCard } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { cn } from "@/lib/utils"

interface ChatMessage {
  role: string
  content: string
  message_id?: string
  streaming?: boolean
}

export default function CourseInfoPage() {
  const { kbId } = useParams<{ kbId: string }>()
  const [card, setCard] = useState<CourseInfoCard | null>(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState("")
  const [deleting, setDeleting] = useState(false)

  // Chat
  const [chatInput, setChatInput] = useState("")
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [chatStreaming, setChatStreaming] = useState(false)
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [enableThinking, setEnableThinking] = useState(false)
  const [historyConvs, setHistoryConvs] = useState<ConversationInfo[]>([])
  const abortRef = useRef<(() => void) | null>(null)
  const chatEndRef = useRef<HTMLDivElement>(null)

  const loadCard = async () => {
    if (!kbId) return
    setLoading(true)
    try {
      const c = await getCourseInfoCard(kbId)
      setCard(c)
    } catch {
      setCard(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadCard() }, [kbId])

  useEffect(() => {
    if (!kbId) return
    listConversations(kbId, "course_info").then(setHistoryConvs).catch(() => {})
  }, [kbId, conversationId])

  const handleGenerate = async () => {
    if (!kbId) return
    setGenerating(true)
    setError("")
    try {
      const c = await generateCourseInfoCard(kbId)
      setCard(c)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setGenerating(false)
    }
  }

  const handleDelete = async () => {
    if (!kbId || !window.confirm("确认重置课程信息卡片？")) return
    setDeleting(true)
    try {
      await deleteCourseInfoCard(kbId)
      setCard(null)
      setChatMessages([])
      setConversationId(null)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setDeleting(false)
    }
  }

  const handleSwitchConv = async (convId: string) => {
    if (!kbId) return
    setConversationId(convId)
    setChatMessages([])
    try {
      const conv = await getConversation(convId)
      const msgs: ChatMessage[] = []
      for (const m of conv.messages || []) {
        if (m.role === "user" || m.role === "assistant") {
          msgs.push({ role: m.role, content: m.content, message_id: m.message_id })
        }
      }
      setChatMessages(msgs)
    } catch { /* ignore */ }
  }

  const handleFork = async (messageId: string) => {
    if (!conversationId) return
    try {
      const forked = await forkConversation(conversationId, messageId, "")
      listConversations(kbId!, "course_info").then(setHistoryConvs)
      await handleSwitchConv(forked.conversation_id)
    } catch (e) {
      alert("Fork 失败：" + (e as Error).message)
    }
  }

  const handleChat = () => {
    if (!kbId || !chatInput.trim() || chatStreaming) return
    const q = chatInput.trim()
    setChatInput("")
    setChatStreaming(true)

    setChatMessages(prev => [
      ...prev,
      { role: "user", content: q },
      { role: "assistant", content: "", streaming: true },
    ])
    let accContent = ""

    abortRef.current = streamCourseInfoChat(kbId, q, conversationId, {
      enableThinking,
      onEvent(evt: ChatEvent) {
        if (evt.type === "delta") {
          accContent += evt.content
          setChatMessages(prev => {
            const idx = prev.findLastIndex(m => m.streaming)
            if (idx === -1) return prev
            const next = [...prev]
            next[idx] = { ...next[idx], content: accContent }
            return next
          })
        }
      },
      onError(err) {
        setChatMessages(prev => {
          const idx = prev.findLastIndex(m => m.streaming)
          if (idx === -1) return [...prev, { role: "assistant", content: `错误: ${err.message}` }]
          const next = [...prev]
          next[idx] = { role: "assistant", content: `错误: ${err.message}` }
          return next
        })
        setChatStreaming(false)
      },
      onDone(newConvId) {
        if (newConvId) setConversationId(newConvId)
        setChatStreaming(false)
        // Mark last streaming message as done
        setChatMessages(prev => prev.map(m => m.streaming ? { ...m, streaming: false } : m))
      },
      onMessageId(msgId) {
        setChatMessages(prev => {
          const idx = prev.findLastIndex(m => m.role === "assistant")
          if (idx === -1) return prev
          const next = [...prev]
          next[idx] = { ...next[idx], message_id: msgId }
          return next
        })
      },
    })

    setTimeout(() => chatEndRef.current?.scrollIntoView({ behavior: "smooth" }), 100)
  }

  const pctToStr = (v: number) => v > 0 ? `${Math.round(v * 100)}%` : "未知"

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-gray-400">
        <Spinner className="mr-2" /> 加载中…
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-3xl mx-auto">
        <div className="mb-5 flex items-center justify-between">
          <h1 className="text-xl font-bold text-gray-900">课程管家</h1>
          <div className="flex gap-2">
            {card && (
              <>
                <Button size="sm" variant="outline" onClick={handleGenerate} disabled={generating}>
                  <RefreshCw className={cn("h-4 w-4 mr-1", generating && "animate-spin")} />
                  重新生成
                </Button>
                <Button size="sm" variant="outline" className="text-red-500 hover:text-red-600" onClick={handleDelete} disabled={deleting}>
                  <Trash2 className="h-4 w-4 mr-1" />重置
                </Button>
              </>
            )}
          </div>
        </div>

        {error && (
          <div className="mb-4 rounded-lg bg-red-50 border border-red-200 text-red-700 p-3 text-sm">⚠ {error}</div>
        )}

        {!card && !generating && (
          <div className="rounded-xl border-2 border-dashed border-gray-200 p-12 text-center">
            <MessageSquare className="mx-auto mb-3 h-10 w-10 opacity-40 text-gray-400" />
            <p className="text-gray-500 mb-4">尚未生成课程信息卡片</p>
            <p className="text-sm text-gray-400 mb-6">
              点击下方按钮，AI 将自动从本知识库中提取课程名称、老师信息、考核方式、截止日期等
            </p>
            <Button onClick={handleGenerate}>生成课程信息卡片</Button>
          </div>
        )}

        {generating && (
          <div className="rounded-xl border bg-white p-12 text-center">
            <Loader2 className="mx-auto mb-3 h-8 w-8 animate-spin text-blue-500" />
            <p className="text-gray-600">AI 正在提取课程信息…（约 10-30 秒）</p>
          </div>
        )}

        {card && (
          <div className="space-y-4 mb-6">
            {/* 基本信息 */}
            <div className="rounded-xl border bg-white p-5">
              <h2 className="text-base font-semibold text-gray-800 mb-3">{card.course_name || "课程信息"}</h2>
              <div className="grid grid-cols-1 gap-2 text-sm">
                {card.instructor && (
                  <div className="flex items-start gap-2">
                    <User className="h-4 w-4 text-gray-400 mt-0.5 shrink-0" />
                    <div><span className="text-gray-500">任课老师：</span><span className="text-gray-800">{card.instructor}</span></div>
                  </div>
                )}
                {card.contact && (
                  <div className="flex items-start gap-2">
                    <Mail className="h-4 w-4 text-gray-400 mt-0.5 shrink-0" />
                    <div><span className="text-gray-500">联系方式：</span><span className="text-gray-800 whitespace-pre-wrap">{card.contact}</span></div>
                  </div>
                )}
              </div>
            </div>

            {/* 考核方式 */}
            {card.assessment && (
              <div className="rounded-xl border bg-white p-5">
                <div className="flex items-center gap-2 mb-3">
                  <BarChart3 className="h-4 w-4 text-blue-500" />
                  <h3 className="text-sm font-semibold text-gray-700">考核方式</h3>
                </div>
                <div className="flex gap-3 mb-2">
                  {card.assessment.exam_ratio > 0 && (
                    <div className="flex-1 rounded-lg bg-blue-50 p-3 text-center">
                      <div className="text-xl font-bold text-blue-600">{pctToStr(card.assessment.exam_ratio)}</div>
                      <div className="text-xs text-gray-500">期末考试</div>
                    </div>
                  )}
                  {card.assessment.hw_ratio > 0 && (
                    <div className="flex-1 rounded-lg bg-green-50 p-3 text-center">
                      <div className="text-xl font-bold text-green-600">{pctToStr(card.assessment.hw_ratio)}</div>
                      <div className="text-xs text-gray-500">作业</div>
                    </div>
                  )}
                  {card.assessment.attendance_ratio > 0 && (
                    <div className="flex-1 rounded-lg bg-amber-50 p-3 text-center">
                      <div className="text-xl font-bold text-amber-600">{pctToStr(card.assessment.attendance_ratio)}</div>
                      <div className="text-xs text-gray-500">出勤</div>
                    </div>
                  )}
                </div>
                {card.assessment.description && (
                  <p className="text-xs text-gray-500 mt-2">{card.assessment.description}</p>
                )}
              </div>
            )}

            {/* 截止日期 */}
            {card.deadlines_normalized && card.deadlines_normalized.length > 0 && (
              <div className="rounded-xl border bg-white p-5">
                <div className="flex items-center gap-2 mb-3">
                  <Calendar className="h-4 w-4 text-amber-500" />
                  <h3 className="text-sm font-semibold text-gray-700">截止日期</h3>
                </div>
                <div className="space-y-2">
                  {card.deadlines_normalized.map((dl, i) => (
                    <div key={i} className={cn(
                      "flex items-center justify-between rounded-lg px-3 py-2 text-sm",
                      dl.days_left !== undefined && dl.days_left !== null && dl.days_left <= 3
                        ? "bg-red-50 border border-red-100" : "bg-gray-50"
                    )}>
                      <div>
                        <span className="font-medium text-gray-800">{dl.name}</span>
                        {dl.date_text && <span className="ml-2 text-xs text-gray-400">({dl.date_text})</span>}
                      </div>
                      {dl.days_left !== undefined && dl.days_left !== null ? (
                        <span className={cn(
                          "text-xs rounded-full px-2 py-0.5",
                          dl.days_left <= 0 ? "bg-red-100 text-red-600" :
                          dl.days_left <= 3 ? "bg-orange-100 text-orange-600" :
                          "bg-gray-100 text-gray-500"
                        )}>
                          {dl.days_left <= 0 ? "已截止" : dl.days_left === 1 ? "明天" : `${dl.days_left}天后`}
                        </span>
                      ) : (
                        <span className="text-xs text-gray-400">{dl.date || "日期未知"}</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 重要通知 */}
            {card.important_notes && (
              <div className="rounded-xl border bg-white p-5">
                <div className="flex items-center gap-2 mb-3">
                  <AlertCircle className="h-4 w-4 text-red-400" />
                  <h3 className="text-sm font-semibold text-gray-700">重要通知</h3>
                </div>
                <p className="text-sm text-gray-700 whitespace-pre-wrap">{card.important_notes}</p>
              </div>
            )}
          </div>
        )}

        {/* Chat section */}
        {card && (
          <div className="rounded-xl border bg-white">
            <div className="border-b px-4 py-3 flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold text-gray-700">课程问答</h2>
                <p className="text-xs text-gray-400">基于课程信息卡片进行多轮问答</p>
              </div>
              {/* 历史会话切换 */}
              {historyConvs.length > 1 && (
                <div className="flex items-center gap-1">
                  <span className="text-xs text-gray-400">历史：</span>
                  <select
                    className="text-xs border rounded px-1 py-0.5 max-w-[120px] truncate"
                    value={conversationId || ""}
                    onChange={e => e.target.value && handleSwitchConv(e.target.value)}
                  >
                    <option value="">新对话</option>
                    {historyConvs.map(c => (
                      <option key={c.conversation_id} value={c.conversation_id}>
                        {c.title || c.conversation_id.slice(0, 8)}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            <div className="max-h-72 overflow-y-auto p-4 space-y-3">
              {chatMessages.length === 0 && (
                <p className="text-xs text-gray-400 text-center py-4">
                  你可以问："作业怎么提交？" "期末考什么时候？" "老师邮箱是多少？" 等
                </p>
              )}
              {chatMessages.map((m, i) => (
                <div key={i} className={cn("text-sm", m.role === "user" ? "text-right" : "text-left")}>
                  <div className={cn(
                    "inline-block rounded-lg px-3 py-2 max-w-[85%] text-left",
                    m.role === "user" ? "bg-blue-500 text-white" : "bg-gray-100 text-gray-800"
                  )}>
                    {m.role === "assistant" ? (
                      <>
                        {m.content
                          ? <div className="md-prose prose prose-sm max-w-none"><ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown></div>
                          : <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                        {!m.streaming && m.message_id && (
                          <button
                            onClick={() => handleFork(m.message_id!)}
                            className="mt-1 flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600"
                            title="从此处分叉新对话"
                          >
                            <GitBranch className="h-3 w-3" />Fork
                          </button>
                        )}
                      </>
                    ) : m.content}
                  </div>
                </div>
              ))}
              <div ref={chatEndRef} />
            </div>

            <div className="border-t p-3 flex gap-2">
              <Input
                className="flex-1 h-8 text-sm"
                placeholder="问关于课程的任何问题…"
                value={chatInput}
                onChange={e => setChatInput(e.target.value)}
                onKeyDown={e => e.key === "Enter" && !e.shiftKey && handleChat()}
                disabled={chatStreaming}
              />
              <Button
                size="sm"
                variant={enableThinking ? "default" : "outline"}
                className="shrink-0"
                onClick={() => setEnableThinking(v => !v)}
                title={enableThinking ? "已开启思维链（点击关闭）" : "开启思维链（深度思考模式）"}
              >
                <Brain className="h-4 w-4" />
              </Button>
              <Button size="sm" onClick={handleChat} disabled={chatStreaming || !chatInput.trim()}>
                {chatStreaming ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
