// 检索透视 Retrieval X-Ray（v1.4.0）
// 把隐藏的检索链路揭开做成可视化：LLM 查询规划 → 关键词(BM25)+向量 双路 → RRF → 重排。
// 两态：演示态（脊柱式分阶段动画，唬人）/ 开发态（密集数据表，评估算法）。

import { useCallback, useEffect, useRef, useState } from "react"
import { useParams, useSearchParams } from "react-router-dom"
import { AnimatePresence, motion } from "motion/react"
import {
  ScanSearch, Play, Pause, RotateCcw, ChevronLeft, ChevronRight,
  Sparkles, Table2, Loader2, AlertCircle, Gauge, History,
} from "lucide-react"
import { retrieveTrace } from "@/api/client"
import type { RetrievalTraceResponse } from "@/api/types"
import { Btn } from "@/components/Modal"
import { cn } from "@/lib/utils"
import {
  StageQuery, StageKeyword, StageVector, StageFusion, StageRerank, StageFinal,
} from "@/components/xray/DemoStages"
import { DevTables } from "@/components/xray/DevTables"

const STAGES = [StageQuery, StageKeyword, StageVector, StageFusion, StageRerank, StageFinal]
const TOTAL = STAGES.length
const TOPK_OPTIONS = [3, 5, 8, 10]

// 演示节奏：每阶段停留时长（ms）。演示是动画叙事，刻意比真实耗时慢，给观众思考时间。
const SPEED_MS = { slow: 3400, normal: 2300, fast: 1300 } as const
type Speed = keyof typeof SPEED_MS
const SPEED_LABEL: Record<Speed, string> = { slow: "慢", normal: "中", fast: "快" }

export default function RetrievalXrayPage() {
  const { kbId } = useParams<{ kbId: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const [query, setQuery] = useState("")
  const [topK, setTopK] = useState(5)
  const [data, setData] = useState<RetrievalTraceResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [mode, setMode] = useState<"demo" | "dev">("demo")
  const [revealed, setRevealed] = useState(0)
  const [auto, setAuto] = useState(false)
  const [speed, setSpeed] = useState<Speed>("normal")
  const inputRef = useRef<HTMLInputElement>(null)
  const stageRefs = useRef<(HTMLDivElement | null)[]>([])
  const [history, setHistory] = useState<string[]>([])

  useEffect(() => {
    if (!kbId) return
    const raw = localStorage.getItem(`xray_history_${kbId}`)
    if (raw) {
      try {
        setHistory(JSON.parse(raw))
      } catch (e) {}
    } else {
      setHistory([])
    }
  }, [kbId])

  // 演示态分阶段自动播放（节奏可调）
  useEffect(() => {
    if (mode !== "demo" || !data || !auto || revealed >= TOTAL) return
    const t = setTimeout(() => setRevealed((r) => Math.min(TOTAL, r + 1)), revealed === 0 ? 450 : SPEED_MS[speed])
    return () => clearTimeout(t)
  }, [mode, data, auto, revealed, speed])

  // 视角自动跟随当前阶段（仿大模型流式输出时视角停在正在输出那一行）
  useEffect(() => {
    if (mode !== "demo" || revealed < 1) return
    const el = stageRefs.current[revealed - 1]
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center" })
  }, [revealed, mode])

  const runQuery = useCallback(async (rawQuery: string, k: number) => {
    const q = rawQuery.trim()
    if (!q || !kbId) return
    setLoading(true)
    setError(null)
    setRevealed(0)
    setAuto(false)
    try {
      const res = await retrieveTrace(kbId, q, k)
      setData(res)
      setRevealed(0)
      setAuto(true) // 演示态自动开播
      setHistory((prev) => {
        const next = [q, ...prev.filter((x) => x !== q)].slice(0, 20)
        localStorage.setItem(`xray_history_${kbId}`, JSON.stringify(next))
        return next
      })
    } catch (e) {
      setError((e as Error).message || "检索失败")
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [kbId])

  const run = () => { if (!loading) runQuery(query, topK) }

  // 深链：从对话页「透视本次检索」带 ?q=（+可选 ?k=）进来 → 自动填入并跑透视
  useEffect(() => {
    const q = searchParams.get("q")
    if (!q || !kbId) return
    const kRaw = Number(searchParams.get("k"))
    const k = TOPK_OPTIONS.includes(kRaw) ? kRaw : topK
    setQuery(q)
    setTopK(k)
    runQuery(q, k)
    setSearchParams({}, { replace: true }) // 清掉 query，避免刷新/回退重复跑
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kbId])

  const playing = auto && revealed < TOTAL
  const togglePlay = () => {
    if (revealed >= TOTAL) {
      setRevealed(0)
      setAuto(true)
    } else {
      setAuto((a) => !a)
    }
  }
  const step = (dir: 1 | -1) => {
    setAuto(false)
    setRevealed((r) => Math.max(0, Math.min(TOTAL, r + dir)))
  }

  const trace = data?.trace
  const empty = trace && trace.counts.final === 0

  return (
    <div className="flex h-full">
      {/* 左：检索历史 */}
      <aside className="hidden w-56 shrink-0 flex-col border-r border-border bg-surface/40 p-3.5 sm:flex">
        <div className="mb-3 flex items-center justify-between px-1">
          <h2 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-ink-faint">
            <History className="h-3.5 w-3.5" />
            检索历史
          </h2>
          {history.length > 0 && (
            <button
              onClick={() => {
                if (confirm("确定清除所有检索历史吗？")) {
                  setHistory([])
                  localStorage.removeItem(`xray_history_${kbId}`)
                }
              }}
              className="text-[10px] text-ink-faint hover:text-accent"
            >
              清空
            </button>
          )}
        </div>
        {history.length === 0 ? (
          <p className="px-1 py-6 text-center text-xs text-ink-faint">暂无检索历史</p>
        ) : (
          <div className="space-y-1 overflow-y-auto pr-0.5">
            {history.map((h, i) => (
              <button
                key={i}
                onClick={() => {
                  setQuery(h)
                  runQuery(h, topK)
                }}
                className={cn(
                  "block w-full truncate rounded-xl px-3 py-2 text-left text-xs transition-all",
                  query === h ? "bg-accent-soft text-accent font-medium" : "text-ink-soft hover:bg-surface-2",
                )}
                title={h}
              >
                {h}
              </button>
            ))}
          </div>
        )}
      </aside>

      {/* 右：内容 */}
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-4xl px-5 py-7 sm:px-8">
        {/* 标题 */}
        <header className="mb-6">
          <div className="flex items-center gap-2.5">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent-soft text-accent">
              <ScanSearch className="h-5 w-5" />
            </span>
            <div>
              <h1 className="font-display text-2xl font-semibold text-ink">检索透视</h1>
              <p className="text-sm text-ink-soft">
                看清一个问题如何被拆解、双路召回、融合与重排 —— 不是「调个 API」那么简单
              </p>
            </div>
          </div>
        </header>

        {/* 查询条 */}
        <div className="card mb-6 p-3 shadow-card">
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex min-w-[240px] flex-1 items-center gap-2 rounded-xl border border-border bg-surface px-3">
              <ScanSearch className="h-4 w-4 shrink-0 text-ink-faint" />
              <input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && run()}
                placeholder="输入一个问题，透视它的检索全过程…"
                className="w-full bg-transparent py-2.5 text-sm text-ink placeholder:text-ink-faint focus:outline-none"
              />
            </div>
            <div className="flex items-center gap-1 rounded-xl border border-border bg-surface px-2 py-1.5">
              <span className="px-1 text-[11px] font-medium text-ink-faint">top-K</span>
              {TOPK_OPTIONS.map((k) => (
                <button
                  key={k}
                  onClick={() => setTopK(k)}
                  className={cn(
                    "h-7 w-7 rounded-lg font-mono text-xs font-medium transition-colors",
                    topK === k ? "bg-accent text-accent-ink" : "text-ink-soft hover:bg-surface-2",
                  )}
                >
                  {k}
                </button>
              ))}
            </div>
            <Btn onClick={run} disabled={!query.trim() || loading}>
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ScanSearch className="h-4 w-4" />}
              透视
            </Btn>
          </div>
        </div>

        {/* 错误 */}
        {error && (
          <div className="mb-6 flex items-start gap-2 rounded-lg border border-border bg-surface px-4 py-3 text-sm text-accent">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* 空状态（未检索） */}
        {!data && !loading && !error && <EmptyHint />}

        {/* 加载骨架 */}
        {loading && (
          <div className="flex flex-col items-center justify-center gap-3 py-20 text-ink-soft">
            <Loader2 className="h-7 w-7 animate-spin text-accent" />
            <p className="text-sm">正在跑通规划 → 双路召回 → 融合 → 重排…</p>
          </div>
        )}

        {/* 结果 */}
        {trace && !loading && (
          <>
            {/* 工具条：两态切换 + 演示播放控制 */}
            <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
              <div className="inline-flex rounded-xl border border-border bg-surface p-1">
                <ModeBtn active={mode === "demo"} onClick={() => setMode("demo")} icon={<Sparkles className="h-3.5 w-3.5" />}>
                  演示态
                </ModeBtn>
                <ModeBtn active={mode === "dev"} onClick={() => setMode("dev")} icon={<Table2 className="h-3.5 w-3.5" />}>
                  开发态
                </ModeBtn>
              </div>

              {mode === "demo" && !empty && (
                <div className="flex items-center gap-1.5">
                  <div className="mr-1 inline-flex items-center rounded-lg border border-border bg-surface p-0.5">
                    <Gauge className="ml-1 mr-0.5 h-3.5 w-3.5 text-ink-faint" />
                    {(Object.keys(SPEED_MS) as Speed[]).map((s) => (
                      <button
                        key={s}
                        onClick={() => setSpeed(s)}
                        className={cn(
                          "h-6 rounded-md px-2 text-[11px] font-medium transition-colors",
                          speed === s ? "bg-accent-soft text-accent" : "text-ink-faint hover:text-ink-soft",
                        )}
                        title={`节奏：${SPEED_LABEL[s]}`}
                      >
                        {SPEED_LABEL[s]}
                      </button>
                    ))}
                  </div>
                  <IconBtn onClick={() => step(-1)} disabled={revealed === 0} label="上一步">
                    <ChevronLeft className="h-4 w-4" />
                  </IconBtn>
                  <button
                    onClick={togglePlay}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-accent-ink transition-all hover:brightness-105"
                  >
                    {revealed >= TOTAL ? (
                      <><RotateCcw className="h-3.5 w-3.5" /> 重播</>
                    ) : playing ? (
                      <><Pause className="h-3.5 w-3.5" /> 暂停</>
                    ) : (
                      <><Play className="h-3.5 w-3.5" /> 播放</>
                    )}
                  </button>
                  <IconBtn onClick={() => step(1)} disabled={revealed >= TOTAL} label="下一步">
                    <ChevronRight className="h-4 w-4" />
                  </IconBtn>
                  <span className="ml-1 font-mono text-xs text-ink-faint">{Math.min(revealed, TOTAL)} / {TOTAL}</span>
                </div>
              )}
            </div>

            {empty ? (
              <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-surface py-16 text-center text-ink-soft">
                <AlertCircle className="h-6 w-6 text-ink-faint" />
                <p className="text-sm">没有检索到相关内容。</p>
                <p className="text-xs text-ink-faint">确认该知识库已完成解析与索引，或换一个更贴合资料的问题。</p>
              </div>
            ) : (
              <AnimatePresence mode="wait">
                {mode === "demo" ? (
                  <motion.div
                    key="demo"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                  >
                    {STAGES.map((Stage, i) => (
                      <div key={i} ref={(el) => { stageRefs.current[i] = el }} className="scroll-mt-24">
                        <Stage
                          trace={trace}
                          docs={data.docs}
                          state={revealed > i ? "active" : "pending"}
                          current={revealed === i + 1}
                        />
                      </div>
                    ))}
                  </motion.div>
                ) : (
                  <motion.div
                    key="dev"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                  >
                    <DevTables trace={trace} docs={data.docs} />
                  </motion.div>
                )}
              </AnimatePresence>
            )}
          </>
        )}
      </div>
    </div>
  </div>
  )
}

// ── 小部件 ──────────────────────────────────────────────────

function ModeBtn({
  active, onClick, icon, children,
}: {
  active: boolean
  onClick: () => void
  icon: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
        active ? "bg-accent-soft text-accent" : "text-ink-soft hover:text-ink",
      )}
    >
      {icon}
      {children}
    </button>
  )
}

function IconBtn({
  children, onClick, disabled, label,
}: {
  children: React.ReactNode
  onClick: () => void
  disabled?: boolean
  label: string
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      className="flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-surface text-ink-soft transition-colors hover:text-ink disabled:opacity-40"
    >
      {children}
    </button>
  )
}

function EmptyHint() {
  const steps = [
    { n: "1", t: "查询规划", d: "LLM 拆关键词 + 写假设答案" },
    { n: "2", t: "双路召回", d: "BM25 关键词 + 语义向量并行" },
    { n: "3", t: "RRF 融合", d: "两路名次倒数相加" },
    { n: "4", t: "重排终选", d: "qwen3-rerank 深读重排" },
  ]
  return (
    <div className="rounded-xl border border-dashed border-border-strong bg-surface/40 px-6 py-12 text-center">
      <ScanSearch className="mx-auto mb-3 h-8 w-8 text-ink-faint" />
      <p className="mb-1 font-display text-lg font-semibold text-ink">输入一个问题，开始透视</p>
      <p className="mx-auto mb-7 max-w-md text-sm text-ink-soft">
        同样一句提问，背后要经过四个隐藏阶段才能找到最相关的资料。下面就是这条链路。
      </p>
      <div className="mx-auto grid max-w-2xl grid-cols-2 gap-3 sm:grid-cols-4">
        {steps.map((s) => (
          <div key={s.n} className="rounded-lg border border-border bg-surface p-3 text-left shadow-card">
            <span className="mb-1.5 flex h-6 w-6 items-center justify-center rounded-full bg-accent-soft font-mono text-xs font-semibold text-accent">
              {s.n}
            </span>
            <p className="text-sm font-semibold text-ink">{s.t}</p>
            <p className="mt-0.5 text-[11px] leading-relaxed text-ink-faint">{s.d}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
