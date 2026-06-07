// 解析透视 · 检视面板（右栏）
// 四态：①未选 → 文档总览 + 隐藏流水线叙事 + 图例；②选 section → 小节归属/父子切片；
// ③选 block → 块解析详情（类型/坐标/文本/图片 VLM 描述）+ 父切片 & 命中子切片；
// ④选 parent（点中间父块大框）→ 父块视图：全文 + 成员块 + 子切片 + 资产 + 检索索引管理。

import { useState } from "react"
import { AnimatePresence, motion } from "motion/react"
import {
  AlertTriangle, BookOpen, Boxes, Check, ChevronDown, Code2, FileText, GitBranch,
  HelpCircle, Image as ImageIcon, ImageOff, Layers, ListTree, Loader2, MapPin,
  PanelRightClose, Pencil, Plus, RefreshCw, ScanLine, Sigma, Sparkles, Table2, Tag,
  Trash2, Type, X, Zap, type LucideIcon,
} from "lucide-react"
import type {
  ChildChunkRow, ExtraIndex, ExtraIndexKind, IRBlock, IRResponse, IRSection, ParentChunkRow,
} from "@/api/types"
import {
  createDocIndex, deleteDocIndex, getAssetUrl, patchDocIndex,
  regenerateDocIndex, toggleDocIndex,
} from "@/api/client"
import { cn } from "@/lib/utils"
import {
  crumb, isImageType, legendItems, sectionLabel, truncate, typeMeta,
  type DerivedMaps,
} from "./helpers"
import { BlockTypeBadge, LevelTag, TypeDot } from "./badges"

export function Inspector({
  ir, maps, kbId, docId, parentCount, childCount,
  selectedBlock, selectedSection, selectedParentId, indexesByParent,
  onSelectBlock, onSelectSection, onSelectParent, onRefreshIndexes, onCollapse,
}: {
  ir: IRResponse
  maps: DerivedMaps
  kbId: string
  docId: string
  parentCount: number
  childCount: number
  selectedBlock: IRBlock | null
  selectedSection: IRSection | null
  selectedParentId: string | null
  indexesByParent: Record<string, ExtraIndex[]>
  onSelectBlock: (id: string) => void
  onSelectSection: (id: string) => void
  onSelectParent: (id: string) => void
  onRefreshIndexes: () => void
  onCollapse?: () => void
}) {
  const selectedParent = (selectedParentId && maps.parentById.get(selectedParentId)) || null

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b border-border px-3.5 py-3">
        <ScanLine className="h-4 w-4 text-accent" />
        <h2 className="font-display text-sm font-semibold text-ink">解析检视</h2>
        {onCollapse && (
          <button onClick={onCollapse} title="收起检视面板"
            className="-mr-1 ml-auto flex h-6 w-6 items-center justify-center rounded text-ink-faint transition-colors hover:text-ink">
            <PanelRightClose className="h-4 w-4" />
          </button>
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-3.5 py-3.5">
        {selectedBlock ? (
          <BlockView
            ir={ir} maps={maps} kbId={kbId} docId={docId}
            block={selectedBlock} onSelectBlock={onSelectBlock}
            onSelectSection={onSelectSection} onSelectParent={onSelectParent}
          />
        ) : selectedSection ? (
          <SectionView
            maps={maps} section={selectedSection}
            onSelectBlock={onSelectBlock} onSelectSection={onSelectSection} onSelectParent={onSelectParent}
          />
        ) : selectedParent ? (
          <ParentView
            ir={ir} maps={maps} kbId={kbId} docId={docId} parent={selectedParent}
            indexes={indexesByParent[selectedParent.parent_chunk_id] ?? []}
            onSelectBlock={onSelectBlock} onSelectSection={onSelectSection}
            onRefreshIndexes={onRefreshIndexes}
          />
        ) : (
          <OverviewView ir={ir} maps={maps} parentCount={parentCount} childCount={childCount} />
        )}
      </div>
    </div>
  )
}

// ── 通用小件 ────────────────────────────────────────────────

function SectionTitle({ icon: Icon, children }: {
  icon: React.ComponentType<{ className?: string }>; children: React.ReactNode
}) {
  return (
    <h3 className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-faint">
      <Icon className="h-3.5 w-3.5" />
      {children}
    </h3>
  )
}

function CrumbLine({ path, onClick }: { path: string[]; onClick?: () => void }) {
  return (
    <button
      onClick={onClick}
      disabled={!onClick}
      className={cn(
        "flex w-full items-start gap-1.5 rounded-lg bg-surface-2/60 px-2.5 py-2 text-left text-xs leading-relaxed text-ink-soft",
        onClick && "transition-colors hover:text-accent",
      )}
    >
      <MapPin className="mt-0.5 h-3 w-3 shrink-0 text-ink-faint" />
      <span className="break-words">{crumb(path)}</span>
    </button>
  )
}

/** 折叠分区：标题行点击展开/收起，内容 motion 高度过渡。 */
function Collapsible({ icon: Icon, title, subtitle, count, defaultOpen = false, children }: {
  icon: LucideIcon; title: string; subtitle?: string; count?: number
  defaultOpen?: boolean; children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface/50">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-3 py-2.5 text-left transition-colors hover:bg-surface-2/40"
      >
        <Icon className="h-3.5 w-3.5 shrink-0 text-ink-faint" />
        <span className="text-xs font-semibold text-ink">{title}</span>
        {count !== undefined && (
          <span className="rounded-full bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] text-ink-faint">{count}</span>
        )}
        {subtitle && <span className="truncate text-[10px] text-ink-faint">{subtitle}</span>}
        <ChevronDown className={cn("ml-auto h-4 w-4 shrink-0 text-ink-faint transition-transform", open && "rotate-180")} />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <div className="border-t border-border px-3 pb-3 pt-2.5">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

/** 开关：研读室强调色，role=switch 可访问。 */
function Toggle({ on, busy, onChange, title, className }: {
  on: boolean; busy?: boolean; onChange: (v: boolean) => void; title?: string; className?: string
}) {
  return (
    <button
      type="button" role="switch" aria-checked={on} title={title} disabled={busy}
      onClick={() => onChange(!on)}
      className={cn(
        "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors disabled:opacity-50",
        on ? "bg-accent" : "bg-surface-2 ring-1 ring-inset ring-border-strong",
        className,
      )}
    >
      <motion.span
        layout transition={{ type: "spring", stiffness: 500, damping: 32 }}
        className={cn(
          "absolute h-3.5 w-3.5 rounded-full shadow-card",
          on ? "right-[3px] bg-accent-ink" : "left-[3px] bg-ink-faint",
        )}
      />
    </button>
  )
}

function ActionBtn({ icon: Icon, busy, onClick, className, children }: {
  icon: LucideIcon; busy?: boolean; onClick: () => void; className?: string; children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick} disabled={busy}
      className={cn(
        "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] text-ink-faint transition-colors hover:text-accent disabled:opacity-50",
        className,
      )}
    >
      {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Icon className="h-3 w-3" />}
      {children}
    </button>
  )
}

// ── ① 块解析详情 ────────────────────────────────────────────

function BlockView({
  ir, maps, kbId, docId, block, onSelectBlock, onSelectSection, onSelectParent,
}: {
  ir: IRResponse
  maps: DerivedMaps
  kbId: string
  docId: string
  block: IRBlock
  onSelectBlock: (id: string) => void
  onSelectSection: (id: string) => void
  onSelectParent: (id: string) => void
}) {
  const parent = maps.parentByBlock.get(block.block_id) ?? null
  const childHits = maps.childrenByBlock.get(block.block_id) ?? []
  const [x0, y0, x1, y1] = block.bbox_norm1000.length >= 4 ? block.bbox_norm1000 : [0, 0, 0, 0]
  const hasBox = x1 > x0 && y1 > y0

  return (
    <div className="space-y-4">
      {/* 头 */}
      <div>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <BlockTypeBadge type={block.type} size="md" />
          <span className="font-mono text-[11px] text-ink-faint">
            p.{block.page_idx + 1} · #{block.order_in_doc}
          </span>
          {block.role && block.role !== "main" && (
            <span className="rounded bg-surface-2 px-1.5 py-0.5 text-[10px] text-ink-faint">{block.role}</span>
          )}
        </div>
        <CrumbLine
          path={block.header_path}
          onClick={block.section_id ? () => onSelectSection(block.section_id) : undefined}
        />
        {hasBox && (
          <p className="mt-1.5 px-1 font-mono text-[10px] text-ink-faint">
            bbox <span className="text-ink-soft">[{x0.toFixed(0)}, {y0.toFixed(0)}, {x1.toFixed(0)}, {y1.toFixed(0)}]</span> / 1000
          </p>
        )}
      </div>

      {/* 内容 */}
      {isImageType(block.type) ? (
        <div className="space-y-2.5">
          {block.assets[0] ? (
            <img
              src={getAssetUrl(kbId, docId, block.assets[0])}
              alt="图片块"
              className="w-full rounded-lg border border-border bg-surface object-contain"
            />
          ) : (
            <div className="flex h-32 items-center justify-center rounded-lg border border-border bg-surface-2 text-ink-faint">
              <ImageOff className="h-6 w-6" />
            </div>
          )}
          {block.vlm_description ? (
            <div className="rounded-lg border border-accent/25 bg-accent-soft/50 p-3">
              <p className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold text-accent-strong">
                <Sparkles className="h-3.5 w-3.5" /> 我们的 VLM 描述
              </p>
              <p className="whitespace-pre-wrap text-xs leading-relaxed text-ink-soft">{block.vlm_description}</p>
            </div>
          ) : (
            <p className="rounded-lg border border-border bg-surface-2/60 p-3 text-xs text-ink-faint">
              {ir.enriched ? "该图未生成 VLM 描述" : "basic IR（未做图片 VLM 富化）"}
            </p>
          )}
          {block.text && (
            <div>
              <SectionTitle icon={Type}>MinerU caption</SectionTitle>
              <p className="whitespace-pre-wrap rounded-lg border border-border bg-surface px-3 py-2 text-xs leading-relaxed text-ink-soft">{block.text}</p>
            </div>
          )}
        </div>
      ) : block.table_html ? (
        <div>
          <SectionTitle icon={Type}>表格</SectionTitle>
          <div
            className="md-prose md-compact max-h-72 overflow-auto rounded-lg border border-border bg-surface p-3"
            // 表格 HTML 来自我们自己的解析产物
            dangerouslySetInnerHTML={{ __html: block.table_html }}
          />
        </div>
      ) : (
        <div>
          <SectionTitle icon={Type}>原文</SectionTitle>
          <p className="whitespace-pre-wrap break-words rounded-lg border border-border bg-surface px-3 py-2.5 text-sm leading-relaxed text-ink">
            {block.text || <span className="italic text-ink-faint">（空文本块）</span>}
          </p>
        </div>
      )}

      {/* 切片归属 */}
      <div>
        <SectionTitle icon={Layers}>父切片（Big Context）</SectionTitle>
        {parent ? (
          <ParentCard parent={parent} childCount={(maps.childrenByParent.get(parent.parent_chunk_id) ?? []).length}
            onClick={() => onSelectParent(parent.parent_chunk_id)} />
        ) : (
          <p className="rounded-lg border border-dashed border-border bg-surface-2/40 px-3 py-2.5 text-xs text-ink-faint">
            此块未并入任何父切片（标题块不单列、容器小节不出父块）
          </p>
        )}
      </div>

      <div>
        <SectionTitle icon={Boxes}>命中它的子切片（向量检索单元）</SectionTitle>
        {childHits.length ? (
          <div className="space-y-1.5">
            {childHits.map((c) => (
              <ChildCard key={c.child_chunk_id} child={c} sourceBlocks={c.source_block_ids.length}
                onSelectBlock={onSelectBlock} currentBlockId={block.block_id} />
            ))}
          </div>
        ) : (
          <p className="rounded-lg border border-dashed border-border bg-surface-2/40 px-3 py-2.5 text-xs text-ink-faint">
            未生成子切片（如标题块仅作 header_path 前缀，不单独向量化）
          </p>
        )}
      </div>
    </div>
  )
}

// ── ② 小节归属 ──────────────────────────────────────────────

function SectionView({
  maps, section, onSelectBlock, onSelectSection, onSelectParent,
}: {
  maps: DerivedMaps
  section: IRSection
  onSelectBlock: (id: string) => void
  onSelectSection: (id: string) => void
  onSelectParent: (id: string) => void
}) {
  const members = maps.blocksBySection.get(section.section_id) ?? []
  const parent = [...maps.parentById.values()].find((p) => p.section_id === section.section_id) ?? null
  const childList = parent ? (maps.childrenByParent.get(parent.parent_chunk_id) ?? []) : []
  const typeCounts = new Map<string, number>()
  for (const b of members) typeCounts.set(b.type, (typeCounts.get(b.type) ?? 0) + 1)

  return (
    <div className="space-y-4">
      <div>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <LevelTag level={section.level || 1} />
          {section.synthetic && (
            <span className="rounded bg-surface-2 px-1.5 py-0.5 text-[10px] italic text-ink-faint">synthetic</span>
          )}
          {section.page_span?.length >= 1 && (
            <span className="font-mono text-[11px] text-ink-faint">
              p.{section.page_span[0] + 1}{section.page_span.length > 1 && section.page_span[1] !== section.page_span[0] ? `–${section.page_span[1] + 1}` : ""}
            </span>
          )}
        </div>
        <h3 className="font-display text-base font-semibold leading-snug text-ink">{sectionLabel(section)}</h3>
        <div className="mt-2"><CrumbLine path={section.header_path} /></div>
      </div>

      {/* 成员块类型分布 */}
      {typeCounts.size > 0 && (
        <div>
          <SectionTitle icon={Boxes}>成员块（{members.length}）</SectionTitle>
          <div className="flex flex-wrap gap-1.5">
            {[...typeCounts.entries()].map(([t, n]) => (
              <span key={t} className="inline-flex items-center gap-1 rounded-md bg-surface-2 px-1.5 py-0.5 text-[10px] text-ink-soft">
                <TypeDot type={t} />{typeMeta(t).label} <span className="font-mono text-ink-faint">{n}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* 父切片 */}
      <div>
        <SectionTitle icon={Layers}>父切片</SectionTitle>
        {parent ? (
          <ParentCard parent={parent} childCount={childList.length}
            onClick={() => onSelectParent(parent.parent_chunk_id)} />
        ) : (
          <p className="rounded-lg border border-dashed border-border bg-surface-2/40 px-3 py-2.5 text-xs text-ink-faint">
            该小节不单独成父切片（纯标题容器 / 无正文内容）
          </p>
        )}
      </div>

      {/* 子切片 */}
      {childList.length > 0 && (
        <div>
          <SectionTitle icon={Boxes}>子切片（{childList.length}）</SectionTitle>
          <div className="space-y-1.5">
            {childList.map((c) => (
              <ChildCard key={c.child_chunk_id} child={c} sourceBlocks={c.source_block_ids.length}
                onSelectBlock={onSelectBlock} />
            ))}
          </div>
        </div>
      )}

      {/* 成员块清单 */}
      {members.length > 0 && (
        <div>
          <SectionTitle icon={ListTree}>逐块</SectionTitle>
          <div className="space-y-1">
            {members.map((b) => (
              <button
                key={b.block_id}
                onClick={() => onSelectBlock(b.block_id)}
                className="flex w-full items-center gap-2 rounded-lg border border-border bg-surface px-2.5 py-1.5 text-left transition-colors hover:border-border-strong"
              >
                <TypeDot type={b.type} />
                <span className="min-w-0 flex-1 truncate text-xs text-ink-soft">
                  {b.text ? truncate(b.text, 50) : `（${typeMeta(b.type).label}）`}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {section.child_section_ids.length > 0 && (
        <button
          onClick={() => onSelectSection(section.child_section_ids[0])}
          className="flex items-center gap-1.5 text-xs text-accent transition-colors hover:text-accent-strong"
        >
          <GitBranch className="h-3.5 w-3.5" /> 含 {section.child_section_ids.length} 个子小节
        </button>
      )}
    </div>
  )
}

// ── ③ 父块视图（点中间父块大框）─────────────────────────────

const ASSET_TYPES = new Set(["image", "table", "code", "equation"])

function ParentView({
  ir, maps, kbId, docId, parent, indexes, onSelectBlock, onSelectSection, onRefreshIndexes,
}: {
  ir: IRResponse
  maps: DerivedMaps
  kbId: string
  docId: string
  parent: ParentChunkRow
  indexes: ExtraIndex[]
  onSelectBlock: (id: string) => void
  onSelectSection: (id: string) => void
  onRefreshIndexes: () => void
}) {
  const members = (parent.block_ids ?? [])
    .map((id) => maps.blockById.get(id))
    .filter((b): b is IRBlock => !!b)
  const children = maps.childrenByParent.get(parent.parent_chunk_id) ?? []
  const assetBlocks = members.filter((b) => ASSET_TYPES.has(b.type))
  const text = parent.text_for_generation || ""
  const span = parent.page_span ?? []
  const title = parent.title?.trim() || parent.header_path?.filter(Boolean).slice(-1)[0] || "（无标题父块）"

  return (
    <div className="space-y-4">
      {/* 头 */}
      <div>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-accent-soft px-2.5 py-1 text-xs font-semibold text-accent-strong">
            <Layers className="h-3.5 w-3.5" /> 父块
          </span>
          <span className="font-mono text-[11px] text-ink-faint">{parent.parent_chunk_id.slice(0, 8)}</span>
          {span.length >= 1 && (
            <span className="font-mono text-[11px] text-ink-faint">
              p.{span[0] + 1}{span.length > 1 && span[1] !== span[0] ? `–${span[1] + 1}` : ""}
            </span>
          )}
        </div>
        <h3 className="font-display text-base font-semibold leading-snug text-ink">{title}</h3>
        <div className="mt-2">
          <CrumbLine path={parent.header_path} onClick={parent.section_id ? () => onSelectSection(parent.section_id) : undefined} />
        </div>
        <div className="mt-2.5 grid grid-cols-3 gap-1.5">
          <Stat label="成员块" value={members.length} />
          <Stat label="子切片" value={children.length} />
          <Stat label="字数" value={text.length} />
        </div>
      </div>

      {/* 检索索引管理（主角）*/}
      <IndexManager
        key={parent.parent_chunk_id}
        parentId={parent.parent_chunk_id} childCount={children.length} assetCount={assetBlocks.length}
        indexes={indexes} kbId={kbId} docId={docId} onRefresh={onRefreshIndexes}
      />

      {/* 父块全文（Small-to-Big 上下文）*/}
      <Collapsible icon={FileText} title="父块全文" subtitle="喂给问答模型">
        <p className="whitespace-pre-wrap break-words text-xs leading-relaxed text-ink-soft">
          {text || <span className="italic text-ink-faint">（空）</span>}
        </p>
      </Collapsible>

      {/* 资产 */}
      {assetBlocks.length > 0 && (
        <Collapsible icon={Sparkles} title="父块资产" count={assetBlocks.length} defaultOpen>
          <AssetList blocks={assetBlocks} kbId={kbId} docId={docId} enriched={ir.enriched} onSelectBlock={onSelectBlock} />
        </Collapsible>
      )}

      {/* 成员 MinerU 块 */}
      <Collapsible icon={ListTree} title="成员 MinerU 块" count={members.length}>
        <div className="space-y-1">
          {members.map((b) => (
            <button
              key={b.block_id}
              onClick={() => onSelectBlock(b.block_id)}
              className="flex w-full items-center gap-2 rounded-lg border border-border bg-surface px-2.5 py-1.5 text-left transition-colors hover:border-border-strong"
            >
              <TypeDot type={b.type} />
              <span className="min-w-0 flex-1 truncate text-xs text-ink-soft">
                {b.text ? truncate(b.text, 48) : `（${typeMeta(b.type).label}）`}
              </span>
              <span className="shrink-0 font-mono text-[9px] text-ink-faint">p.{b.page_idx + 1}</span>
            </button>
          ))}
        </div>
      </Collapsible>

      {/* 常规子切片 */}
      {children.length > 0 && (
        <Collapsible icon={Boxes} title="常规子切片" count={children.length}>
          <div className="space-y-1.5">
            {children.map((c) => (
              <ChildCard key={c.child_chunk_id} child={c} sourceBlocks={c.source_block_ids.length}
                onSelectBlock={onSelectBlock} />
            ))}
          </div>
        </Collapsible>
      )}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-surface px-2 py-1.5 text-center">
      <p className="font-mono text-sm font-semibold tabular-nums text-ink">{value}</p>
      <p className="text-[10px] text-ink-faint">{label}</p>
    </div>
  )
}

function AssetList({ blocks, kbId, docId, enriched, onSelectBlock }: {
  blocks: IRBlock[]; kbId: string; docId: string; enriched: boolean; onSelectBlock: (id: string) => void
}) {
  return (
    <div className="space-y-2">
      {blocks.map((b) => (
        <button
          key={b.block_id}
          onClick={() => onSelectBlock(b.block_id)}
          className="flex w-full items-start gap-2.5 rounded-lg border border-border bg-surface p-2 text-left transition-colors hover:border-accent/40"
        >
          {b.type === "image" && b.assets[0] ? (
            <img src={getAssetUrl(kbId, docId, b.assets[0])} alt="资产" className="h-14 w-14 shrink-0 rounded-md border border-border object-cover" />
          ) : (
            <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-md border border-border bg-surface-2">
              {b.type === "table" ? <Table2 className="h-5 w-5 text-ink-faint" />
                : b.type === "code" ? <Code2 className="h-5 w-5 text-ink-faint" />
                : b.type === "equation" ? <Sigma className="h-5 w-5 text-ink-faint" />
                : <ImageIcon className="h-5 w-5 text-ink-faint" />}
            </span>
          )}
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <BlockTypeBadge type={b.type} />
              {b.type === "image" && (
                <span className="rounded bg-accent-soft px-1.5 py-0.5 text-[9px] font-medium text-accent-strong">→ 多模态原图</span>
              )}
            </div>
            <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-ink-faint">
              {b.type === "image"
                ? (b.vlm_description || (enriched ? "（无 VLM 描述）" : "basic IR 未富化"))
                : (b.text || `（${typeMeta(b.type).label}）`)}
            </p>
          </div>
        </button>
      ))}
    </div>
  )
}

// ── 检索索引管理 ────────────────────────────────────────────

interface KindMeta { label: string; Icon: LucideIcon; hint: string; cost?: boolean }
const KIND_META: Record<ExtraIndexKind, KindMeta> = {
  summary: { label: "摘要索引", Icon: BookOpen, hint: "LLM 浓缩父块要点，换种问法也更易命中" },
  hypo_question: { label: "推测问题索引", Icon: HelpCircle, hint: "LLM 推测读者会问的问题（可预答）", cost: true },
  custom: { label: "自定义索引", Icon: Tag, hint: "你手填的检索文本" },
}
const AUTO_KINDS: ExtraIndexKind[] = ["summary", "hypo_question"]

function IndexManager({ parentId, childCount, assetCount, indexes, kbId, docId, onRefresh }: {
  parentId: string; childCount: number; assetCount: number
  indexes: ExtraIndex[]; kbId: string; docId: string; onRefresh: () => void
}) {
  const enabledCount = indexes.filter((i) => i.enabled).length + 1 // +1 常规子块始终在用
  const byKind = (k: ExtraIndexKind) => indexes.filter((i) => i.kind === k)
  const customs = byKind("custom")

  return (
    <div className="rounded-xl border border-accent/25 bg-accent-soft/25 p-3">
      <div className="mb-1.5 flex items-center gap-2">
        <Zap className="h-4 w-4 text-accent" />
        <h3 className="font-display text-sm font-semibold text-ink">检索索引</h3>
        <span className="ml-auto inline-flex items-center gap-1 rounded-full bg-surface px-2 py-0.5 text-[10px] text-ink-faint">
          <span className="h-1.5 w-1.5 rounded-full bg-success" /> {enabledCount} 路在用
        </span>
      </div>
      <p className="mb-3 text-[11px] leading-relaxed text-ink-faint">
        召回该父块的不同「入口」。启用即物化为虚拟子块并入混合检索，命中后经 Small-to-Big 回到整块上下文。
      </p>

      {/* 常规子块（始终参与，不可关）*/}
      <div className="mb-2 flex items-center gap-2 rounded-lg border border-border bg-surface px-3 py-2">
        <Boxes className="h-3.5 w-3.5 text-ink-faint" />
        <span className="text-xs text-ink-soft">常规子块索引</span>
        <span className="font-mono text-[10px] text-ink-faint">× {childCount}</span>
        <span className="ml-auto inline-flex items-center gap-1 text-[10px] text-success">
          <Check className="h-3 w-3" /> 始终参与
        </span>
      </div>

      {/* 图/表描述已在常规子块中自动索引（每图/表各成独立子块，retrieval_text=VLM 描述）*/}
      {assetCount > 0 && (
        <p className="mb-2 flex items-start gap-1.5 rounded-lg bg-surface-2/50 px-3 py-2 text-[10px] leading-relaxed text-ink-faint">
          <ImageIcon className="mt-0.5 h-3 w-3 shrink-0" />
          <span>本父块的 {assetCount} 个图/表已由 VLM 生成描述、各成 1 个常规子块按描述检索（见下方「父块资产」），无需另建索引。</span>
        </p>
      )}

      {/* 各类附加索引：摘要 / 推测问题 / 自定义 */}
      <div className="space-y-2">
        {AUTO_KINDS.map((kind) => {
          const existing = byKind(kind)
          if (existing.length) {
            return existing.map((ix) => (
              <IndexCard key={ix.index_id} index={ix} kbId={kbId} docId={docId} onRefresh={onRefresh} />
            ))
          }
          return <GenerateRow key={kind} kind={kind} parentId={parentId} kbId={kbId} docId={docId} onRefresh={onRefresh} />
        })}

        {customs.map((ix) => (
          <IndexCard key={ix.index_id} index={ix} kbId={kbId} docId={docId} onRefresh={onRefresh} />
        ))}
        <AddCustomRow parentId={parentId} kbId={kbId} docId={docId} onRefresh={onRefresh} />
      </div>
    </div>
  )
}

function IndexCard({ index, kbId, docId, onRefresh }: {
  index: ExtraIndex; kbId: string; docId: string; onRefresh: () => void
}) {
  const meta = KIND_META[index.kind]
  const [busy, setBusy] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(index.index_text)
  const [confirmDel, setConfirmDel] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const isHypo = index.kind === "hypo_question"
  const questions = index.payload?.questions ?? []
  const answers = index.payload?.answers ?? []

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true); setErr(null)
    try { await fn(); onRefresh() }
    catch (e) { setErr((e as Error).message || "操作失败") }
    finally { setBusy(false) }
  }

  return (
    <div className={cn(
      "rounded-lg border bg-surface p-2.5 transition-colors",
      index.enabled ? "border-accent/45 shadow-[inset_2px_0_0_var(--color-accent)]" : "border-border",
    )}>
      <div className="flex items-center gap-2">
        <meta.Icon className={cn("h-3.5 w-3.5 shrink-0", index.enabled ? "text-accent" : "text-ink-faint")} />
        <span className="truncate text-xs font-medium text-ink">{index.title || meta.label}</span>
        {index.enabled && (
          <span className="shrink-0 rounded-full bg-accent-soft px-1.5 py-0.5 text-[9px] font-semibold text-accent-strong">检索中</span>
        )}
        <Toggle
          on={index.enabled} busy={busy} className="ml-auto"
          title={index.enabled ? "停用（移出检索）" : "启用（并入检索）"}
          onChange={(v) => run(() => toggleDocIndex(kbId, docId, index.index_id, v))}
        />
      </div>

      {/* 内容 */}
      {editing ? (
        <div className="mt-2">
          <textarea
            value={draft} onChange={(e) => setDraft(e.target.value)} rows={5}
            className="w-full resize-y rounded-lg border border-border bg-bg px-2.5 py-2 text-xs leading-relaxed text-ink focus:outline-none focus:ring-2 focus:ring-accent/40"
          />
          <div className="mt-1.5 flex gap-1.5">
            <button
              disabled={busy || !draft.trim()}
              onClick={() => run(async () => { await patchDocIndex(kbId, docId, index.index_id, { index_text: draft.trim() }); setEditing(false) })}
              className="inline-flex items-center gap-1 rounded-md bg-accent px-2.5 py-1 text-[10px] font-semibold text-accent-ink disabled:opacity-50"
            >
              {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />} 保存
            </button>
            <button onClick={() => { setEditing(false); setDraft(index.index_text) }}
              className="inline-flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-[10px] text-ink-soft hover:text-ink">
              <X className="h-3 w-3" /> 取消
            </button>
          </div>
        </div>
      ) : isHypo && questions.length > 0 ? (
        <ul className="mt-2 space-y-1.5">
          {questions.map((q, i) => (
            <li key={i} className="text-[11px] leading-relaxed text-ink-soft">
              <span className="font-semibold text-accent">Q{i + 1}.</span> {q}
              {answers[i] && <p className="mt-0.5 pl-4 text-[10px] text-ink-faint">{answers[i]}</p>}
            </li>
          ))}
        </ul>
      ) : (
        <button onClick={() => setExpanded((s) => !s)} className="mt-1.5 block w-full text-left">
          <p className={cn("whitespace-pre-wrap break-words text-[11px] leading-relaxed text-ink-soft", !expanded && "line-clamp-2")}>
            {index.index_text || <span className="italic text-ink-faint">（空）</span>}
          </p>
        </button>
      )}

      {/* 操作 */}
      {!editing && (
        <div className="mt-2 flex items-center gap-1.5">
          {!isHypo && (
            <ActionBtn icon={Pencil} onClick={() => { setDraft(index.index_text); setEditing(true) }}>编辑</ActionBtn>
          )}
          {index.kind !== "custom" && (
            <ActionBtn icon={RefreshCw} busy={busy} onClick={() => run(() => regenerateDocIndex(kbId, docId, index.index_id, isHypo && answers.length > 0))}>
              重生成
            </ActionBtn>
          )}
          {confirmDel ? (
            <span className="ml-auto flex items-center gap-2 text-[10px]">
              <span className="text-warn">删除?</span>
              <button onClick={() => run(() => deleteDocIndex(kbId, docId, index.index_id))} className="font-semibold text-warn hover:underline">确认</button>
              <button onClick={() => setConfirmDel(false)} className="text-ink-faint hover:text-ink">取消</button>
            </span>
          ) : (
            <ActionBtn icon={Trash2} className="ml-auto hover:!text-warn" onClick={() => setConfirmDel(true)}>删除</ActionBtn>
          )}
        </div>
      )}
      {err && <p className="mt-1.5 text-[10px] text-warn">{err}</p>}
    </div>
  )
}

function GenerateRow({ kind, parentId, kbId, docId, onRefresh }: {
  kind: ExtraIndexKind; parentId: string; kbId: string; docId: string; onRefresh: () => void
}) {
  const meta = KIND_META[kind]
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [withAnswer, setWithAnswer] = useState(false)

  const gen = async () => {
    setBusy(true); setErr(null)
    try {
      await createDocIndex(kbId, docId, {
        parent_chunk_id: parentId, kind,
        with_answer: kind === "hypo_question" ? withAnswer : undefined,
      })
      onRefresh()
    } catch (e) { setErr((e as Error).message || "生成失败") }
    finally { setBusy(false) }
  }

  return (
    <div className="rounded-lg border border-dashed border-border bg-surface/40 p-2.5">
      <div className="flex items-center gap-2">
        <meta.Icon className="h-3.5 w-3.5 shrink-0 text-ink-faint" />
        <span className="text-xs text-ink-soft">{meta.label}</span>
        {meta.cost && (
          <span className="inline-flex items-center gap-0.5 rounded bg-warn/15 px-1.5 py-0.5 text-[9px] font-medium text-warn">
            <AlertTriangle className="h-2.5 w-2.5" /> 耗 API
          </span>
        )}
        <button
          disabled={busy} onClick={gen}
          className="ml-auto inline-flex items-center gap-1 rounded-md bg-accent px-2.5 py-1 text-[10px] font-semibold text-accent-ink transition-opacity disabled:opacity-40"
        >
          {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Plus className="h-3 w-3" />} 生成
        </button>
      </div>
      <p className="mt-1 text-[10px] leading-relaxed text-ink-faint">{meta.hint}</p>
      {kind === "hypo_question" && (
        <label className="mt-1.5 flex w-fit cursor-pointer items-center gap-1.5 text-[10px] text-ink-soft">
          <input type="checkbox" checked={withAnswer} onChange={(e) => setWithAnswer(e.target.checked)} className="accent-[var(--color-accent)]" />
          附预答（让模型提前作答，更耗 API）
        </label>
      )}
      {err && <p className="mt-1 text-[10px] text-warn">{err}</p>}
    </div>
  )
}

function AddCustomRow({ parentId, kbId, docId, onRefresh }: {
  parentId: string; kbId: string; docId: string; onRefresh: () => void
}) {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState("")
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const add = async () => {
    if (!text.trim()) return
    setBusy(true); setErr(null)
    try {
      await createDocIndex(kbId, docId, { parent_chunk_id: parentId, kind: "custom", custom_text: text.trim() })
      setText(""); setOpen(false); onRefresh()
    } catch (e) { setErr((e as Error).message || "添加失败") }
    finally { setBusy(false) }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-dashed border-border py-2 text-[11px] text-ink-faint transition-colors hover:border-accent/40 hover:text-accent"
      >
        <Plus className="h-3.5 w-3.5" /> 添加自定义索引
      </button>
    )
  }
  return (
    <div className="rounded-lg border border-accent/30 bg-surface p-2.5">
      <div className="mb-1.5 flex items-center gap-1.5">
        <Tag className="h-3.5 w-3.5 text-accent" />
        <span className="text-xs font-medium text-ink">自定义索引</span>
      </div>
      <textarea
        value={text} onChange={(e) => setText(e.target.value)} rows={3} autoFocus
        placeholder="用于召回该父块的检索文本：同义改写、别名、关键词…"
        className="w-full resize-y rounded-lg border border-border bg-bg px-2.5 py-2 text-xs leading-relaxed text-ink placeholder:text-ink-faint focus:outline-none focus:ring-2 focus:ring-accent/40"
      />
      <div className="mt-1.5 flex gap-1.5">
        <button
          disabled={busy || !text.trim()} onClick={add}
          className="inline-flex items-center gap-1 rounded-md bg-accent px-2.5 py-1 text-[10px] font-semibold text-accent-ink disabled:opacity-50"
        >
          {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />} 添加
        </button>
        <button onClick={() => { setOpen(false); setText("") }}
          className="inline-flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-[10px] text-ink-soft hover:text-ink">
          <X className="h-3 w-3" /> 取消
        </button>
      </div>
      {err && <p className="mt-1 text-[10px] text-warn">{err}</p>}
    </div>
  )
}

// ── ④ 文档总览 ──────────────────────────────────────────────

function OverviewView({ ir, maps, parentCount, childCount }: {
  ir: IRResponse; maps: DerivedMaps; parentCount: number; childCount: number
}) {
  const imageBlocks = ir.blocks.filter((b) => isImageType(b.type)).length
  const steps = [
    { icon: FileText, title: "MinerU 解析", desc: `${ir.blocks.length} 个版面块，精准坐标锚定` },
    { icon: GitBranch, title: "LLM 文档树重建", desc: `${ir.sections.length} 个小节，多级层级（非扁平）` },
    { icon: Layers, title: "结构感知切片", desc: `${parentCount} 父块 / ${childCount} 子块，父子显式映射` },
    { icon: Sparkles, title: "图片 VLM 适配", desc: imageBlocks ? `${imageBlocks} 张图，描述替换原位再入库` : "本文档无图片" },
  ]
  const legend = legendItems(maps.usedTypes)

  return (
    <div className="space-y-5">
      <p className="text-sm leading-relaxed text-ink-soft">
        一份文档要经过这条隐藏流水线，才能被检索与回答。点左侧文档树或中间版面框，逐块透视；
        点父块大框可管理它的<span className="font-medium text-accent">检索索引</span>。
      </p>

      <div className="relative space-y-0">
        {steps.map((s, i) => (
          <div key={i} className="relative flex gap-3 pb-4 last:pb-0">
            <div className="relative flex flex-col items-center">
              <span className="z-10 flex h-8 w-8 items-center justify-center rounded-full border border-accent/30 bg-accent-soft text-accent">
                <s.icon className="h-4 w-4" />
              </span>
              {i < steps.length - 1 && <span className="w-px flex-1 bg-border" />}
            </div>
            <div className="pt-0.5">
              <p className="text-sm font-semibold text-ink">{s.title}</p>
              <p className="mt-0.5 text-xs leading-relaxed text-ink-faint">{s.desc}</p>
            </div>
          </div>
        ))}
      </div>

      {legend.length > 0 && (
        <div>
          <SectionTitle icon={Boxes}>版面块类型</SectionTitle>
          <div className="grid grid-cols-2 gap-1.5">
            {legend.map((it) => (
              <span key={it.type} className="inline-flex items-center gap-1.5 rounded-md bg-surface-2/60 px-2 py-1 text-[11px] text-ink-soft">
                <TypeDot type={it.type} />{it.label}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── 切片卡 ──────────────────────────────────────────────────

function ParentCard({ parent, childCount, onClick }: {
  parent: ParentChunkRow; childCount: number; onClick?: () => void
}) {
  const text = parent.text_for_generation || ""
  return (
    <button
      onClick={onClick}
      disabled={!onClick}
      className={cn(
        "block w-full rounded-lg border border-border bg-surface p-3 text-left",
        onClick && "transition-colors hover:border-accent/40",
      )}
    >
      <div className="mb-1.5 flex items-center gap-2 text-[10px] text-ink-faint">
        <span className="font-mono">{parent.parent_chunk_id.slice(0, 8)}</span>
        <span className="rounded bg-surface-2 px-1.5 py-0.5">{childCount} 子块</span>
        <span className="font-mono">{text.length} 字</span>
        {onClick && <span className="ml-auto inline-flex items-center gap-0.5 text-accent">父块视图 <ChevronDown className="h-3 w-3 -rotate-90" /></span>}
      </div>
      <p className="line-clamp-4 whitespace-pre-wrap text-xs leading-relaxed text-ink-soft">
        {text || <span className="italic text-ink-faint">（空）</span>}
      </p>
    </button>
  )
}

function ChildCard({ child, sourceBlocks, onSelectBlock, currentBlockId }: {
  child: ChildChunkRow; sourceBlocks: number
  onSelectBlock: (id: string) => void; currentBlockId?: string
}) {
  const others = child.source_block_ids.filter((b) => b !== currentBlockId)
  return (
    <div className="rounded-lg border border-border bg-surface p-2.5">
      <div className="mb-1 flex items-center gap-2">
        <BlockTypeBadge type={child.chunk_type} />
        <span className="font-mono text-[10px] text-ink-faint">{child.child_chunk_id.slice(0, 8)}</span>
        <span className="ml-auto font-mono text-[10px] text-ink-faint">{sourceBlocks} 源块</span>
      </div>
      <p className="line-clamp-3 whitespace-pre-wrap text-xs leading-relaxed text-ink-soft">
        {child.retrieval_text || <span className="italic text-ink-faint">（空）</span>}
      </p>
      {others.length > 0 && (
        <button
          onClick={() => onSelectBlock(others[0])}
          className="mt-1.5 text-[10px] text-accent transition-colors hover:text-accent-strong"
        >
          + 另 {others.length} 个源块
        </button>
      )}
    </div>
  )
}
