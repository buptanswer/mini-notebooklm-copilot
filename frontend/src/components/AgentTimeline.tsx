import { useState } from "react"
import { AnimatePresence, motion } from "motion/react"
import {
  Brain, CheckCircle2, ChevronRight, ClipboardList, Database, HelpCircle, Loader2,
  PencilLine, Route, Search, AlertTriangle,
} from "lucide-react"
import type { LucideIcon } from "lucide-react"
import type { AgentStepData } from "@/api/types"
import { cn } from "@/lib/utils"

/**
 * 多轮检索 Agent「决策透视」时间线。
 * QA（conversation_service 的 `agent` 事件）与课程管家卡片生成（`progress` 事件）共用。
 * 把"规划 → 检索 → 自评 → 补检索 → 收敛"的 ReAct 闭环做成可视化，取代命令行式日志。
 *
 * variant="inline"（问答内联）：流式时只显当前阶段，完成后自动收成可展开按钮（像思维链，省版面）。
 * variant="card"  （课程管家生成）：完整展开，作为页面主可视化。
 */

interface StepVisual { Icon: LucideIcon; color: string; ring: string; dot: string }

// 注：dot 用字面量 bg-* 类（不可由 color 动态拼接，否则 Tailwind v4 扫描不到、不生成该类）。
const ACCENT: Omit<StepVisual, "Icon"> = { color: "text-accent", ring: "border-accent", dot: "bg-accent" }
const OK: Omit<StepVisual, "Icon"> = { color: "text-emerald-600", ring: "border-emerald-500", dot: "bg-emerald-500" }
const WARN: Omit<StepVisual, "Icon"> = { color: "text-amber-500", ring: "border-amber-500", dot: "bg-amber-500" }

function visualFor(step: string, status?: string): StepVisual {
  switch (step) {
    case "search":
    case "retrieving":
      return { Icon: Search, ...ACCENT }
    case "queries":
      return { Icon: Route, ...ACCENT }
    case "searching":
      return { Icon: Route, ...ACCENT }
    case "merging":
      return { Icon: Database, ...ACCENT }
    case "evaluating":
      return { Icon: Brain, ...ACCENT }
    case "eval_result":
    case "eval_complete":
      return status === "complete" ? { Icon: CheckCircle2, ...OK } : { Icon: HelpCircle, ...WARN }
    case "planning":
      return { Icon: Route, ...WARN }
    case "extracting":
      return { Icon: PencilLine, ...ACCENT }
    case "done":
      return status === "complete" ? { Icon: CheckCircle2, ...OK } : { Icon: AlertTriangle, ...WARN }
    default:
      return { Icon: ClipboardList, ...ACCENT }
  }
}

function roundLabel(round: AgentStepData["round"]): string {
  if (round === "final") return "收敛 · 整合"
  return `第 ${round} 轮检索`
}

/** 单个时间线节点。 */
function StepNode({ s, isLast, live }: { s: AgentStepData; isLast: boolean; live: boolean }) {
  const { Icon, color, ring, dot } = visualFor(s.step, s.status)
  return (
    <motion.div
      initial={{ opacity: 0, x: -8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
      className="relative"
    >
      <span
        className={cn(
          "absolute -left-[27px] top-0.5 flex h-3.5 w-3.5 items-center justify-center rounded-full border-2 bg-surface",
          isLast ? ring : "border-border",
          isLast && "ring-2 ring-accent-soft",
        )}
      >
        {live
          ? <span className="h-1.5 w-1.5 animate-ping rounded-full bg-accent" />
          : <span className={cn("h-1.5 w-1.5 rounded-full", dot)} />}
      </span>

      <div className={cn("rounded-xl border p-3", isLast ? "border-border bg-surface-2/70" : "border-border/40 bg-surface-2/30")}>
        <div className="flex items-center gap-2">
          <Icon className={cn("h-3.5 w-3.5 shrink-0", color, live && "animate-pulse")} />
          <span className="text-[11px] font-semibold text-ink-soft">{roundLabel(s.round)}</span>
          <span className="ml-auto rounded-full bg-border/40 px-1.5 py-0.5 font-mono text-[10px] text-ink-faint">{s.step}</span>
        </div>
        <p className="mt-1.5 text-[13px] leading-relaxed text-ink">{s.message}</p>

        {/* 实际检索词（首轮规划关键词 / 固定 5 槽 / 补检索词） */}
        {s.queries && s.queries.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {s.queries.map((q, qi) => (
              <span key={qi} className="inline-flex items-center gap-1 rounded-md border border-border bg-surface px-1.5 py-0.5 font-mono text-[11px] text-ink-soft">
                <Search className="h-2.5 w-2.5 shrink-0 text-accent" />{q}
              </span>
            ))}
          </div>
        )}

        {/* 缺失分析 */}
        {s.missing_analysis && (
          <div className="mt-2 rounded-lg border border-border/50 bg-surface px-2.5 py-2 text-[12px] text-ink-soft">
            <span className="mb-0.5 block font-semibold text-accent">🔍 缺失信息分析</span>
            <span className="italic leading-normal">{s.missing_analysis}</span>
          </div>
        )}

        {/* 规划的补漏检索词 */}
        {s.new_queries && s.new_queries.length > 0 && (
          <div className="mt-2">
            <span className="text-[11px] font-semibold text-ink-soft">📋 规划补漏检索：</span>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {s.new_queries.map((nq, ni) => (
                <span key={ni} className="rounded-md border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5 font-mono text-[11px] text-amber-700">
                  {nq.query}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </motion.div>
  )
}

/** 完整时间线（含初始化态）。 */
function Timeline({ steps, active }: { steps: AgentStepData[]; active: boolean }) {
  return (
    <div className="relative ml-2.5 space-y-3 border-l border-border/80 pl-5">
      {steps.length === 0 && active && (
        <div className="relative flex items-center gap-2 py-1 text-xs text-ink-soft">
          <span className="absolute -left-[27px] flex h-3.5 w-3.5 items-center justify-center rounded-full border-2 border-accent bg-surface">
            <span className="h-1.5 w-1.5 animate-ping rounded-full bg-accent" />
          </span>
          正在初始化检索上下文…
        </div>
      )}
      {steps.map((s, i) => (
        <StepNode key={i} s={s} isLast={i === steps.length - 1} live={active && i === steps.length - 1 && s.step !== "done"} />
      ))}
    </div>
  )
}

export interface AgentTimelineProps {
  steps: AgentStepData[]
  active?: boolean
  variant?: "card" | "inline"
  title?: string
  subtitle?: string
  className?: string
}

export function AgentTimeline({
  steps, active = false, variant = "card",
  title = "多轮检索 Agent · 决策透视",
  subtitle = "规划 → 双路混合检索 → 自评查漏 → 补检索 → 收敛",
  className,
}: AgentTimelineProps) {
  const [expanded, setExpanded] = useState(false)

  // ── 内联（问答内）：折叠态省版面 ──────────────────────────
  if (variant === "inline") {
    const last = steps[steps.length - 1]
    return (
      <div className={cn("overflow-hidden rounded-xl border border-border/70 bg-surface-2/40", className)}>
        <button
          onClick={() => setExpanded((v) => !v)}
          className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-surface-2/70"
        >
          <Brain className={cn("h-4 w-4 shrink-0 text-accent", active && "animate-pulse")} />
          <span className="text-[13px] font-medium text-ink-soft">
            {active ? "多轮检索 Agent · 决策中" : `多轮检索 Agent · ${steps.length} 步决策`}
          </span>
          {active && <Loader2 className="h-3 w-3 shrink-0 animate-spin text-accent" />}
          <ChevronRight className={cn("ml-auto h-3.5 w-3.5 shrink-0 text-ink-faint transition-transform", expanded && "rotate-90")} />
        </button>

        <AnimatePresence initial={false} mode="wait">
          {expanded ? (
            <motion.div
              key="full"
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.22 }}
              className="overflow-hidden"
            >
              <div className="px-3 pb-3 pt-1">
                <Timeline steps={steps} active={active} />
              </div>
            </motion.div>
          ) : active && last ? (
            // 折叠 + 进行中：只显示当前阶段一行
            <motion.div
              key="cur"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="flex items-center gap-2 px-3 pb-2.5 pl-9 text-[12.5px] text-ink-soft"
            >
              <span className="thinking-shimmer truncate">{last.message}</span>
            </motion.div>
          ) : null}
        </AnimatePresence>
      </div>
    )
  }

  // ── 卡片（课程管家生成）：完整展开 ────────────────────────
  return (
    <div className={cn("relative overflow-hidden rounded-2xl border border-border bg-surface p-5 shadow-card", className)}>
      <div className="pointer-events-none absolute right-0 top-0 h-28 w-28 rounded-full bg-accent/5 blur-3xl" />
      <div className="flex items-center justify-between gap-2 border-b border-border pb-3.5">
        <div className="flex items-center gap-2.5">
          <Brain className={cn("h-5 w-5 text-accent", active && "animate-pulse")} />
          <div className="leading-tight">
            <p className="font-display text-base font-semibold text-ink">{title}</p>
            <p className="text-xs text-ink-faint">{subtitle}</p>
          </div>
        </div>
        {active && (
          <span className="flex items-center gap-1.5 rounded-full bg-accent-soft px-2.5 py-1 text-[11px] font-medium text-accent">
            <Loader2 className="h-3 w-3 animate-spin" />智能决策中
          </span>
        )}
      </div>
      <div className="mt-5">
        <Timeline steps={steps} active={active} />
      </div>
    </div>
  )
}
