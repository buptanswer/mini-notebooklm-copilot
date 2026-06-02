// 解析透视 · 文档树（LLM 重建的层级，交互式 outline）
// 点 section → 联动画布高亮其成员块 + 右栏检视；当前选中块所属 section 自动点亮。

import { useState } from "react"
import { ChevronRight, ListTree, PanelLeftClose } from "lucide-react"
import { cn } from "@/lib/utils"
import { sectionLabel, type TreeNode } from "./helpers"
import { LevelTag } from "./badges"

export function DocTree({
  tree, selectedSectionId, activeSectionId, blockCount, onSelectSection, onCollapse,
}: {
  tree: TreeNode[]
  selectedSectionId: string | null
  activeSectionId: string | null   // 当前选中块所属 section（弱高亮）
  blockCount: (sectionId: string) => number
  onSelectSection: (sectionId: string) => void
  onCollapse?: () => void
}) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-border px-3.5 py-3">
        <ListTree className="h-4 w-4 text-accent" />
        <h2 className="font-display text-sm font-semibold text-ink">文档树</h2>
        <span className="ml-auto rounded-full bg-surface-2 px-2 py-0.5 font-mono text-[10px] text-ink-faint">
          LLM 重建
        </span>
        {onCollapse && (
          <button onClick={onCollapse} title="收起文档树"
            className="-mr-1 flex h-6 w-6 items-center justify-center rounded text-ink-faint transition-colors hover:text-ink">
            <PanelLeftClose className="h-4 w-4" />
          </button>
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-1.5 py-2">
        {tree.length === 0 ? (
          <p className="px-3 py-6 text-center text-xs text-ink-faint">未解析出层级结构</p>
        ) : (
          tree.map((n) => (
            <TreeRow
              key={n.section.section_id}
              node={n}
              selectedSectionId={selectedSectionId}
              activeSectionId={activeSectionId}
              blockCount={blockCount}
              onSelectSection={onSelectSection}
            />
          ))
        )}
      </div>
    </div>
  )
}

function TreeRow({
  node, selectedSectionId, activeSectionId, blockCount, onSelectSection,
}: {
  node: TreeNode
  selectedSectionId: string | null
  activeSectionId: string | null
  blockCount: (sectionId: string) => number
  onSelectSection: (sectionId: string) => void
}) {
  const [open, setOpen] = useState(node.depth < 2)
  const { section } = node
  const hasChildren = node.children.length > 0
  const selected = section.section_id === selectedSectionId
  const active = section.section_id === activeSectionId
  const count = blockCount(section.section_id)

  return (
    <div>
      <div
        className={cn(
          "group mb-0.5 flex items-center gap-1 rounded-lg pr-2 transition-colors",
          selected
            ? "bg-accent-soft"
            : active
              ? "bg-surface-2"
              : "hover:bg-surface-2",
        )}
        style={{ paddingLeft: 6 + node.depth * 13 }}
      >
        <button
          onClick={() => hasChildren && setOpen((v) => !v)}
          className={cn(
            "flex h-5 w-5 shrink-0 items-center justify-center rounded text-ink-faint transition-transform",
            hasChildren ? "hover:text-ink" : "invisible",
            open && "rotate-90",
          )}
          aria-label={open ? "折叠" : "展开"}
        >
          <ChevronRight className="h-3.5 w-3.5" />
        </button>
        <button
          onClick={() => onSelectSection(section.section_id)}
          className="flex min-w-0 flex-1 items-center gap-1.5 py-1.5 text-left"
          title={sectionLabel(section)}
        >
          <LevelTag level={section.level || node.depth + 1} />
          <span
            className={cn(
              "truncate text-xs",
              selected ? "font-semibold text-accent-strong" : "text-ink-soft group-hover:text-ink",
              section.synthetic && "italic text-ink-faint",
            )}
          >
            {sectionLabel(section)}
          </span>
          {count > 0 && (
            <span className="ml-auto shrink-0 font-mono text-[10px] text-ink-faint">{count}</span>
          )}
        </button>
      </div>
      {hasChildren && open && (
        <div className="relative">
          {node.children.map((c) => (
            <TreeRow
              key={c.section.section_id}
              node={c}
              selectedSectionId={selectedSectionId}
              activeSectionId={activeSectionId}
              blockCount={blockCount}
              onSelectSection={onSelectSection}
            />
          ))}
        </div>
      )}
    </div>
  )
}
