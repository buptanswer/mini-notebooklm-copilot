// 解析透视 · 视觉原子（仅组件；纯助手见 ./helpers）

import { typeMeta } from "./helpers"

/** 块类型徽章：用类型层位色描边 + 同色淡填充 + 图标。 */
export function BlockTypeBadge({ type, size = "sm" }: { type?: string; size?: "sm" | "md" }) {
  const { label, color, Icon } = typeMeta(type)
  const pad = size === "md" ? "px-2.5 py-1 text-xs" : "px-2 py-0.5 text-[10px]"
  const icon = size === "md" ? "h-3.5 w-3.5" : "h-3 w-3"
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full font-medium ${pad}`}
      style={{ color, backgroundColor: `${color}1f`, boxShadow: `inset 0 0 0 1px ${color}40` }}
    >
      <Icon className={icon} />
      {label}
    </span>
  )
}

/** 小色点（图例 / 树节点前缀）。 */
export function TypeDot({ type }: { type?: string }) {
  const { color } = typeMeta(type)
  return (
    <span
      className="inline-block h-2.5 w-2.5 shrink-0 rounded-[3px]"
      style={{ backgroundColor: `${color}33`, boxShadow: `inset 0 0 0 1.5px ${color}` }}
    />
  )
}

/** 层级标记 L1/L2/…（文档树）。 */
export function LevelTag({ level }: { level: number }) {
  return (
    <span className="shrink-0 rounded-md bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-ink-faint">
      L{Math.max(1, level)}
    </span>
  )
}

/** 元数据小徽章（页数 / 块数 / 父块数…）。 */
export function MetaPill({ icon: Icon, label, value, tone = "default" }: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: React.ReactNode
  tone?: "default" | "accent"
}) {
  return (
    <span
      className={
        "inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs " +
        (tone === "accent"
          ? "border-accent/30 bg-accent-soft text-accent-strong"
          : "border-border bg-surface text-ink-soft")
      }
    >
      <Icon className="h-3.5 w-3.5 opacity-70" />
      <span className="text-ink-faint">{label}</span>
      <span className="font-mono font-semibold tabular-nums text-ink">{value}</span>
    </span>
  )
}
