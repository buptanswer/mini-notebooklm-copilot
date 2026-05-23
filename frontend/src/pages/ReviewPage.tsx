import { useEffect, useRef, useState } from "react"
import { useParams, useNavigate } from "react-router-dom"
import {
  CalendarDays, BookOpen, ChevronRight, Play, Save, Send,
  RefreshCw, GitBranch, Brain, Loader2, CheckCircle, Printer, FileText,
} from "lucide-react"
import {
  listReviewDates, listReviewSections, streamReviewGenerate, saveReviewNotes,
  streamReviewFollowup, listReviewConversations, forkConversation, getConversation,
  loadReviewNotes,
} from "@/api/client"
import type { ConversationInfo, ReviewDateInfo, ReviewSectionInfo } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Spinner } from "@/components/ui/spinner"
import { cn } from "@/lib/utils"

// 简单 Markdown 渲染（仅做基础格式化）
function MarkdownBlock({ content }: { content: string }) {
  const lines = content.split("\n")
  return (
    <div className="prose prose-sm max-w-none text-sm leading-relaxed">
      {lines.map((line, i) => {
        if (line.startsWith("# ")) return <h1 key={i} className="text-lg font-bold mt-4 mb-2">{line.slice(2)}</h1>
        if (line.startsWith("## ")) return <h2 key={i} className="text-base font-semibold mt-3 mb-1">{line.slice(3)}</h2>
        if (line.startsWith("### ")) return <h3 key={i} className="text-sm font-semibold mt-2 mb-1">{line.slice(4)}</h3>
        if (line.startsWith("- ") || line.startsWith("* ")) return <li key={i} className="ml-4 list-disc">{line.slice(2)}</li>
        if (/^\d+\./.test(line)) return <li key={i} className="ml-4 list-decimal">{line.replace(/^\d+\.\s*/, "")}</li>
        if (line.trim() === "") return <div key={i} className="h-2" />
        return <p key={i}>{line}</p>
      })}
    </div>
  )
}

interface SectionNote {
  section_num: number
  content: string
  done: boolean
  thinking: string
  showThinking: boolean
  message_id?: string
}

export default function ReviewPage() {
  const { kbId, conversationId: urlConvId } = useParams<{ kbId: string; conversationId?: string }>()
  const navigate = useNavigate()

  const [dates, setDates] = useState<ReviewDateInfo[]>([])
  const [selectedDate, setSelectedDate] = useState<string>("")
  const [sections, setSections] = useState<ReviewSectionInfo[]>([])
  const [loadingDates, setLoadingDates] = useState(true)

  // Generation params
  const [timeDescriptor, setTimeDescriptor] = useState("")
  const [userIdentity, setUserIdentity] = useState("北邮通信工程专业大二下")
  const [enableThinking, setEnableThinking] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [generationError, setGenerationError] = useState("")

  // Generated notes per section
  const [sectionNotes, setSectionNotes] = useState<Map<number, SectionNote>>(new Map())
  const [conversationId, setConversationId] = useState<string | null>(urlConvId ?? null)

  // Save state
  const [saving, setSaving] = useState(false)
  const [savedMsg, setSavedMsg] = useState("")

  // Followup chat
  const [followupInput, setFollowupInput] = useState("")
  const [followupMessages, setFollowupMessages] = useState<Array<{role: string; content: string; thinking?: string}>>([])
  const [chatStreaming, setChatStreaming] = useState(false)

  // History
  const [historyConvs, setHistoryConvs] = useState<ConversationInfo[]>([])
  const [showHistory, setShowHistory] = useState(false)

  const abortRef = useRef<(() => void) | null>(null)
  const chatEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!kbId) return
    listReviewDates(kbId).then(d => {
      setDates(d)
      setLoadingDates(false)
    }).catch(() => setLoadingDates(false))
  }, [kbId])

  useEffect(() => {
    if (!kbId) return
    listReviewConversations(kbId).then(setHistoryConvs).catch(() => {})
  }, [kbId, conversationId])

  useEffect(() => {
    if (!kbId || !selectedDate) return
    listReviewSections(kbId, selectedDate).then(setSections).catch(() => {})
  }, [kbId, selectedDate])

  // Load existing notes if navigating to a conversation
  useEffect(() => {
    if (!kbId || !urlConvId) return
    setConversationId(urlConvId)
    getConversation(urlConvId).then(conv => {
      const meta = conv.metadata as Record<string, unknown>
      const date = meta.date as string || ""
      setSelectedDate(date)
      const msgs = conv.messages || []
      const notes = new Map<number, SectionNote>()
      let sectionNum = 1
      msgs.forEach(m => {
        if (m.role === "assistant") {
          const secNum = (m.metadata as Record<string, unknown>)?.section_num as number || sectionNum++
          notes.set(secNum, { section_num: secNum, content: m.content, done: true, thinking: m.thinking || "", showThinking: false, message_id: m.message_id })
        }
      })
      setSectionNotes(notes)
    }).catch(() => {})
  }, [kbId, urlConvId])

  const handleGenerate = () => {
    if (!kbId || !selectedDate || generating) return
    setGenerating(true)
    setGenerationError("")
    setSectionNotes(new Map())
    setConversationId(null)
    setSavedMsg("")

    const currentNotes = new Map<number, SectionNote>()

    abortRef.current = streamReviewGenerate(
      kbId,
      { date: selectedDate, time_descriptor: timeDescriptor, user_identity: userIdentity, enable_thinking: enableThinking },
      {
        onEvent(evt) {
          const type = evt.type as string
          if (type === "conversation_created") {
            setConversationId(evt.conversation_id as string)
          } else if (type === "section_start") {
            const sn = evt.section_num as number
            currentNotes.set(sn, { section_num: sn, content: "", done: false, thinking: "", showThinking: false })
            setSectionNotes(new Map(currentNotes))
          } else if (type === "delta") {
            const sn = evt.section_num as number
            const note = currentNotes.get(sn)
            if (note) {
              note.content += evt.content as string
              currentNotes.set(sn, { ...note })
              setSectionNotes(new Map(currentNotes))
            }
          } else if (type === "thinking") {
            const sn = evt.section_num as number
            const note = currentNotes.get(sn)
            if (note) {
              note.thinking += evt.content as string
              currentNotes.set(sn, { ...note })
              setSectionNotes(new Map(currentNotes))
            }
          } else if (type === "section_done") {
            const sn = evt.section_num as number
            const note = currentNotes.get(sn)
            if (note) {
              note.done = true
              note.message_id = evt.message_id as string
              currentNotes.set(sn, { ...note })
              setSectionNotes(new Map(currentNotes))
            }
          } else if (type === "error") {
            setGenerationError(evt.message as string)
          }
        },
        onError(err) { setGenerationError(err.message); setGenerating(false) },
        onDone() {
          setGenerating(false)
          listReviewDates(kbId!).then(setDates).catch(() => {})
        },
      }
    )
  }

  const handleSave = async () => {
    if (!kbId || !conversationId) return
    setSaving(true)
    try {
      await saveReviewNotes(kbId, conversationId)
      setSavedMsg("讲义已保存到磁盘")
      listReviewDates(kbId).then(setDates)
    } catch (e) {
      setGenerationError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const handleFollowup = () => {
    if (!kbId || !conversationId || !followupInput.trim() || chatStreaming) return
    const q = followupInput.trim()
    setFollowupInput("")
    setChatStreaming(true)

    setFollowupMessages(prev => [...prev, { role: "user", content: q }])
    let accContent = ""
    let accThinking = ""

    abortRef.current = streamReviewFollowup(kbId, conversationId, q, {
      onEvent(evt) {
        if (evt.type === "delta") {
          accContent += evt.content as string
          setFollowupMessages(prev => {
            const last = prev[prev.length - 1]
            if (last?.role === "assistant") {
              return [...prev.slice(0, -1), { ...last, content: accContent }]
            }
            return [...prev, { role: "assistant", content: accContent }]
          })
        } else if (evt.type === "thinking") {
          accThinking += evt.content as string
        }
      },
      onError(err) {
        setFollowupMessages(prev => [...prev, { role: "assistant", content: `错误: ${err.message}` }])
        setChatStreaming(false)
      },
      onDone() { setChatStreaming(false) },
    })

    setTimeout(() => chatEndRef.current?.scrollIntoView({ behavior: "smooth" }), 100)
  }

  const handleFork = async (messageId: string) => {
    if (!conversationId) return
    try {
      const forked = await forkConversation(conversationId, messageId, "")
      alert(`已 Fork 出新会话：${forked.conversation_id}\n（可在历史中找到）`)
      listReviewConversations(kbId!).then(setHistoryConvs)
    } catch (e) {
      alert("Fork 失败：" + (e as Error).message)
    }
  }

  const sortedNotes = Array.from(sectionNotes.values()).sort((a, b) => a.section_num - b.section_num)
  const allDone = sortedNotes.length > 0 && sortedNotes.every(n => n.done)

  return (
    <div className="flex h-full">
      {/* 左侧：日期列表 */}
      <div className="w-52 shrink-0 border-r bg-gray-50 overflow-y-auto p-3">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-gray-700">课堂日期</h2>
          <button
            onClick={() => kbId && listReviewDates(kbId).then(setDates)}
            className="text-gray-400 hover:text-gray-600"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
        </div>

        {loadingDates && <Spinner size="sm" className="mx-auto" />}

        {!loadingDates && dates.length === 0 && (
          <p className="text-xs text-gray-400 text-center mt-4">
            暂无录音文件，请先绑定文件夹并同步
          </p>
        )}

        {dates.map(d => (
          <button
            key={d.date}
            onClick={() => { setSelectedDate(d.date); setSectionNotes(new Map()); setConversationId(null) }}
            className={cn(
              "w-full text-left rounded-lg px-3 py-2 mb-1 text-sm transition-colors",
              selectedDate === d.date ? "bg-blue-100 text-blue-700" : "hover:bg-gray-100 text-gray-700"
            )}
          >
            <div className="flex items-center justify-between">
              <span className="font-medium">{d.date}</span>
              {d.has_notes && <CheckCircle className="h-3.5 w-3.5 text-green-500" />}
            </div>
            <div className="text-xs text-gray-400 mt-0.5">
              {d.section_count} 节 {d.has_notes ? "· 已有讲义" : ""}
            </div>
          </button>
        ))}

        {/* 历史会话 */}
        {historyConvs.length > 0 && (
          <div className="mt-4">
            <button
              onClick={() => setShowHistory(!showHistory)}
              className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 mb-2"
            >
              <ChevronRight className={cn("h-3 w-3 transition-transform", showHistory && "rotate-90")} />
              历史会话 ({historyConvs.length})
            </button>
            {showHistory && historyConvs.map(c => (
              <button
                key={c.conversation_id}
                onClick={() => navigate(`/kb/${kbId}/review/${c.conversation_id}`)}
                className={cn(
                  "w-full text-left rounded px-2 py-1.5 mb-1 text-xs transition-colors",
                  conversationId === c.conversation_id ? "bg-blue-50 text-blue-600" : "hover:bg-gray-100 text-gray-600"
                )}
              >
                {c.title || c.conversation_id.slice(0, 8)}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* 右侧：主内容 */}
      <div className="flex-1 overflow-y-auto p-6">
        {!selectedDate && (
          <div className="flex flex-col items-center justify-center h-full text-gray-400">
            <CalendarDays className="h-12 w-12 mb-3 opacity-40" />
            <p>从左侧选择一个日期开始课后复习</p>
          </div>
        )}

        {selectedDate && (
          <>
            <div className="mb-4 flex items-center justify-between">
              <h1 className="text-xl font-bold text-gray-900">
                {selectedDate} 课后复习
              </h1>
              <div className="flex items-center gap-2">
                {/* 加载已存盘讲义 */}
                {sectionNotes.size === 0 && !generating && dates.find(d => d.date === selectedDate)?.has_notes && (
                  <Button size="sm" variant="outline" onClick={async () => {
                    if (!kbId) return
                    const notes = await loadReviewNotes(kbId, selectedDate).catch(() => [])
                    if (notes.length > 0) {
                      const m = new Map<number, SectionNote>()
                      notes.forEach(n => m.set(n.section_num, {
                        section_num: n.section_num, content: n.content_md,
                        done: true, thinking: "", showThinking: false,
                      }))
                      setSectionNotes(m)
                      setSavedMsg("已加载磁盘讲义")
                    }
                  }}>
                    <FileText className="h-4 w-4 mr-1" />
                    加载已存盘讲义
                  </Button>
                )}
                {allDone && conversationId && (
                  <Button size="sm" variant="outline" onClick={handleSave} disabled={saving}>
                    {saving ? <Spinner size="sm" className="mr-1" /> : <Save className="h-4 w-4 mr-1" />}
                    保存讲义
                  </Button>
                )}
                {allDone && sortedNotes.length > 0 && (
                  <Button size="sm" variant="outline" onClick={() => window.print()} title="导出为 PDF（浏览器打印）">
                    <Printer className="h-4 w-4 mr-1" />
                    导出 PDF
                  </Button>
                )}
              </div>
            </div>

            {savedMsg && (
              <div className="mb-3 rounded-lg bg-green-50 border border-green-200 text-green-700 p-2.5 text-sm">
                ✓ {savedMsg}
              </div>
            )}

            {generationError && (
              <div className="mb-3 rounded-lg bg-red-50 border border-red-200 text-red-700 p-2.5 text-sm">
                ⚠ {generationError}
              </div>
            )}

            {/* 生成参数 */}
            {!generating && sectionNotes.size === 0 && (
              <div className="mb-6 rounded-xl border bg-white p-5 space-y-4">
                <h2 className="text-sm font-semibold text-gray-700">生成参数</h2>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label className="text-xs">上课描述（如"下午2节"）</Label>
                    <Input
                      className="mt-1 h-8 text-sm"
                      placeholder="下午2节"
                      value={timeDescriptor}
                      onChange={e => setTimeDescriptor(e.target.value)}
                    />
                  </div>
                  <div>
                    <Label className="text-xs">身份描述</Label>
                    <Input
                      className="mt-1 h-8 text-sm"
                      placeholder="北邮通信工程专业大二下"
                      value={userIdentity}
                      onChange={e => setUserIdentity(e.target.value)}
                    />
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <label className="flex items-center gap-2 text-sm cursor-pointer">
                    <input
                      type="checkbox"
                      checked={enableThinking}
                      onChange={e => setEnableThinking(e.target.checked)}
                      className="rounded"
                    />
                    <Brain className="h-4 w-4 text-purple-500" />
                    开启思维链
                  </label>
                </div>

                {sections.length > 0 && (
                  <div className="text-xs text-gray-400">
                    共 {sections.length} 节：{sections.map(s => `第${s.section_num}节`).join("、")}
                  </div>
                )}

                <Button onClick={handleGenerate} disabled={sections.length === 0}>
                  <Play className="h-4 w-4 mr-1" />
                  开始生成课后讲义
                </Button>
              </div>
            )}

            {/* 生成中提示 */}
            {generating && (
              <div className="mb-4 flex items-center gap-2 text-sm text-blue-600">
                <Loader2 className="h-4 w-4 animate-spin" />
                正在生成课后讲义…
              </div>
            )}

            {/* 每节讲义 */}
            {sortedNotes.map(note => (
              <div key={note.section_num} className="mb-6 rounded-xl border bg-white overflow-hidden">
                <div className="flex items-center justify-between px-4 py-3 border-b bg-gray-50">
                  <div className="flex items-center gap-2">
                    <BookOpen className="h-4 w-4 text-blue-500" />
                    <span className="font-semibold text-sm">第 {note.section_num} 节</span>
                    {note.done
                      ? <span className="text-xs text-green-600 bg-green-50 px-1.5 py-0.5 rounded">已生成</span>
                      : <span className="text-xs text-blue-600 bg-blue-50 px-1.5 py-0.5 rounded flex items-center gap-1"><Loader2 className="h-3 w-3 animate-spin" />生成中</span>
                    }
                  </div>
                  {note.done && note.message_id && (
                    <button
                      onClick={() => handleFork(note.message_id!)}
                      className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600"
                      title="从此处分叉新对话"
                    >
                      <GitBranch className="h-3.5 w-3.5" />
                      Fork
                    </button>
                  )}
                </div>

                {note.thinking && (
                  <div className="border-b">
                    <button
                      onClick={() => setSectionNotes(prev => {
                        const next = new Map(prev)
                        const n = next.get(note.section_num)!
                        next.set(note.section_num, { ...n, showThinking: !n.showThinking })
                        return next
                      })}
                      className="w-full flex items-center gap-2 px-4 py-2 text-xs text-purple-600 hover:bg-purple-50 text-left"
                    >
                      <Brain className="h-3.5 w-3.5" />
                      {note.showThinking ? "收起" : "展开"}思维链
                    </button>
                    {note.showThinking && (
                      <div className="px-4 pb-3 text-xs text-gray-500 font-mono whitespace-pre-wrap bg-purple-50">
                        {note.thinking}
                      </div>
                    )}
                  </div>
                )}

                <div className="p-4">
                  {note.content
                    ? <MarkdownBlock content={note.content} />
                    : <div className="flex items-center gap-2 text-gray-400 text-sm"><Loader2 className="h-4 w-4 animate-spin" />等待生成…</div>
                  }
                </div>
              </div>
            ))}

            {/* 重新生成按钮 */}
            {!generating && sectionNotes.size > 0 && (
              <Button
                variant="outline"
                size="sm"
                className="mb-6"
                onClick={() => { setSectionNotes(new Map()); setConversationId(null); setSavedMsg("") }}
              >
                <RefreshCw className="h-3.5 w-3.5 mr-1" />
                重新生成
              </Button>
            )}

            {/* 追问区 */}
            {conversationId && allDone && (
              <div className="rounded-xl border bg-white">
                <div className="border-b px-4 py-3">
                  <h2 className="text-sm font-semibold text-gray-700">课后追问</h2>
                  <p className="text-xs text-gray-400">在本次课堂上下文内继续提问</p>
                </div>

                <div className="max-h-64 overflow-y-auto p-4 space-y-3">
                  {followupMessages.map((m, i) => (
                    <div key={i} className={cn("text-sm", m.role === "user" ? "text-right" : "text-left")}>
                      <span className={cn(
                        "inline-block rounded-lg px-3 py-2 max-w-[85%]",
                        m.role === "user" ? "bg-blue-500 text-white" : "bg-gray-100 text-gray-800"
                      )}>
                        {m.content || <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                      </span>
                    </div>
                  ))}
                  <div ref={chatEndRef} />
                </div>

                <div className="border-t p-3 flex gap-2">
                  <Input
                    className="flex-1 h-8 text-sm"
                    placeholder="提问…"
                    value={followupInput}
                    onChange={e => setFollowupInput(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && !e.shiftKey && handleFollowup()}
                    disabled={chatStreaming}
                  />
                  <Button size="sm" onClick={handleFollowup} disabled={chatStreaming || !followupInput.trim()}>
                    <Send className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
