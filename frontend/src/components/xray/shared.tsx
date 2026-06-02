// 检索透视 · 共享视觉组件（研读室体系内）
// 只导出组件（纯助手见 ./helpers）。视觉只用设计 token；动效用 motion。

import type { ReactNode } from "react"
import { motion } from "motion/react"
import { ImageIcon, Table2, Type, Lock } from "lucide-react"
import { cn } from "@/lib/utils"

// ── 切片类型标签 ────────────────────────────────────────────

const TYPE_META: Record<string, { icon: typeof Type; label: string }> = {
  image: { icon: ImageIcon, label: "图片" },
  chart_image: { icon: ImageIcon, label: "图表" },
  chart: { icon: Table2, label: "图表" },
  table: { icon: Table2, label: "表格" },
}

export function ChunkTypeBadge({ type }: { type?: string }) {
  const meta = type ? TYPE_META[type] : undefined
  const Icon = meta?.icon ?? Type
  const label = meta?.label ?? "文本"
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium",
        meta ? "bg-accent-soft text-accent" : "bg-surface-2 text-ink-faint",
      )}
    >
      <Icon className="h-3 w-3" />
      {label}
    </span>
  )
}

// ── 分数条 ──────────────────────────────────────────────────

export function ScoreBar({
  value,
  max,
  min = 0,
  tone = "accent",
  width = 64,
}: {
  value: number
  max: number
  min?: number
  tone?: "accent" | "ink"
  width?: number
}) {
  const pct = max > min ? Math.max(0, Math.min(1, (value - min) / (max - min))) : 0
  return (
    <span className="inline-flex items-center gap-2">
      <span
        className="relative h-1.5 overflow-hidden rounded-full bg-surface-2"
        style={{ width }}
      >
        <motion.span
          className={cn(
            "absolute inset-y-0 left-0 rounded-full",
            tone === "accent" ? "bg-accent" : "bg-ink-faint",
          )}
          initial={{ width: 0 }}
          animate={{ width: `${pct * 100}%` }}
          transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        />
      </span>
      <span className="font-mono text-[11px] tabular-nums text-ink-soft">
        {value.toFixed(3)}
      </span>
    </span>
  )
}

// ── 关键词 chip ─────────────────────────────────────────────

export function KeywordChip({
  word,
  active = false,
  index = 0,
}: {
  word: string
  active?: boolean
  index?: number
}) {
  return (
    <motion.span
      initial={{ opacity: 0, y: 6, scale: 0.9 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ delay: index * 0.06, duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      className={cn(
        "inline-flex items-center rounded-lg border px-2.5 py-1 font-mono text-xs font-medium transition-colors",
        active
          ? "border-accent/40 bg-accent-soft text-accent-strong shadow-card"
          : "border-border bg-surface text-ink-soft",
      )}
    >
      {word}
    </motion.span>
  )
}

// ── 阶段外壳（左侧脊柱 + 站点 + 内容卡）──────────────────────

export function StageShell({
  index,
  icon: Icon,
  title,
  subtitle,
  state,
  current = false,
  isLast = false,
  badge,
  children,
}: {
  index: number
  icon: typeof Type
  title: string
  subtitle: string
  state: "pending" | "active"
  current?: boolean
  isLast?: boolean
  badge?: ReactNode
  children?: ReactNode
}) {
  const active = state === "active"
  return (
    <div className="relative flex gap-4 sm:gap-5">
      {/* 脊柱 + 站点 */}
      <div className="relative flex w-9 shrink-0 flex-col items-center">
        <motion.div
          animate={{
            scale: current ? [1, 1.12, 1] : 1,
          }}
          transition={{ duration: 1.6, repeat: current ? Infinity : 0, ease: "easeInOut" }}
          className={cn(
            "z-10 flex h-9 w-9 items-center justify-center rounded-full border-2 font-mono text-xs font-semibold transition-colors",
            active
              ? "border-accent bg-accent text-accent-ink shadow-raised"
              : "border-border-strong bg-surface text-ink-faint",
          )}
        >
          {active ? <Icon className="h-4 w-4" /> : index}
        </motion.div>
        {!isLast && (
          <div
            className={cn(
              "w-0.5 flex-1 transition-colors",
              active ? "bg-accent/40" : "bg-border",
            )}
          />
        )}
      </div>

      {/* 内容 */}
      <div className={cn("min-w-0 flex-1", isLast ? "pb-2" : "pb-10")}>
        <div className="mb-2 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h3
                className={cn(
                  "font-display text-base font-semibold transition-colors",
                  active ? "text-ink" : "text-ink-faint",
                )}
              >
                {title}
              </h3>
              {!active && <Lock className="h-3 w-3 text-ink-faint" />}
            </div>
            <p
              className={cn(
                "mt-0.5 text-xs leading-relaxed transition-colors",
                active ? "text-ink-soft" : "text-ink-faint/70",
              )}
            >
              {subtitle}
            </p>
          </div>
          {active && badge}
        </div>

        {active && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
            className={cn(
              "rounded-lg border bg-surface p-4 transition-shadow",
              current ? "border-accent/30 shadow-raised" : "border-border shadow-card",
            )}
          >
            {children}
          </motion.div>
        )}
      </div>
    </div>
  )
}

// ── 小计数徽章 ──────────────────────────────────────────────

export function CountBadge({ children }: { children: ReactNode }) {
  return (
    <span className="shrink-0 rounded-full bg-surface-2 px-2.5 py-1 font-mono text-[11px] font-medium text-ink-soft">
      {children}
    </span>
  )
}
