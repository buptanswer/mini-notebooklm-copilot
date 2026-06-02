// 检索透视 · 纯助手（不含组件，便于 fast-refresh 与复用）
// highlightKeywords 返回 JSX，故本文件为 .tsx，但只导出函数、无组件导出。

import type { ReactNode } from "react"
import type { DocMeta } from "@/api/types"

/** 取 doc 文件名（无映射时回退到短 id）。 */
export function docName(docId: string, docs: Record<string, DocMeta>): string {
  return docs[docId]?.filename ?? `${docId.slice(0, 8)}…`
}

/** header_path → 面包屑文本。 */
export function crumb(headerPath: string[]): string {
  return headerPath.filter(Boolean).join(" › ") || "（无标题层级）"
}

export function fmtScore(v: number | null | undefined, digits = 3): string {
  if (v === null || v === undefined) return "—"
  return v.toFixed(digits)
}

export function isImageType(t?: string): boolean {
  return t === "image" || t === "chart_image" || t === "chart"
}

/**
 * 把片段里命中的 token 包成 <mark>，供"关键词匹配"高亮。
 * ASCII token 用词边界（\b），避免 "in" 命中 "printing"；CJK token 直接子串。
 * 传入的应是后端给的 matched_tokens（已是 FTS5 粒度的命中 token）。
 */
export function highlightKeywords(text: string, tokens: string[]): ReactNode[] {
  const toks = tokens.filter(Boolean)
  if (!toks.length) return [text]
  const alts = toks
    .slice()
    .sort((a, b) => b.length - a.length)
    .map((t) => {
      const esc = t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
      return /^[A-Za-z0-9]+$/.test(t) ? `\\b${esc}\\b` : esc
    })
  const re = new RegExp(`(${alts.join("|")})`, "gi")
  const lower = new Set(toks.map((t) => t.toLowerCase()))
  return text.split(re).map((p, i) =>
    p && lower.has(p.toLowerCase()) ? (
      <mark
        key={i}
        className="rounded bg-accent-soft px-0.5 font-medium text-accent-strong"
      >
        {p}
      </mark>
    ) : (
      <span key={i}>{p}</span>
    ),
  )
}
