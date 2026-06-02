// 解析透视 · 检视面板（右栏）
// 三态：①未选 → 文档总览 + 隐藏流水线叙事 + 图例；②选中 section → 小节归属/父子切片；
// ③选中 block → 块解析详情（类型/坐标/文本/图片 VLM 描述）+ 它所属父切片 & 命中的子切片。

import {
  Boxes, FileText, GitBranch, ImageOff, Layers, ListTree, MapPin,
  PanelRightClose, ScanLine, Sparkles, Type,
} from "lucide-react"
import type {
  ChildChunkRow, IRBlock, IRResponse, IRSection, ParentChunkRow,
} from "@/api/types"
import { getAssetUrl } from "@/api/client"
import { cn } from "@/lib/utils"
import {
  crumb, isImageType, legendItems, sectionLabel, truncate, typeMeta,
  type DerivedMaps,
} from "./helpers"
import { BlockTypeBadge, LevelTag, TypeDot } from "./badges"

export function Inspector({
  ir, maps, kbId, docId, parentCount, childCount,
  selectedBlock, selectedSection, onSelectBlock, onSelectSection, onCollapse,
}: {
  ir: IRResponse
  maps: DerivedMaps
  kbId: string
  docId: string
  parentCount: number
  childCount: number
  selectedBlock: IRBlock | null
  selectedSection: IRSection | null
  onSelectBlock: (id: string) => void
  onSelectSection: (id: string) => void
  onCollapse?: () => void
}) {
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
            block={selectedBlock} onSelectBlock={onSelectBlock} onSelectSection={onSelectSection}
          />
        ) : selectedSection ? (
          <SectionView
            maps={maps} section={selectedSection}
            onSelectBlock={onSelectBlock} onSelectSection={onSelectSection}
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

// ── ① 块解析详情 ────────────────────────────────────────────

function BlockView({
  ir, maps, kbId, docId, block, onSelectBlock, onSelectSection,
}: {
  ir: IRResponse
  maps: DerivedMaps
  kbId: string
  docId: string
  block: IRBlock
  onSelectBlock: (id: string) => void
  onSelectSection: (id: string) => void
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
            onClick={parent.section_id ? () => onSelectSection(parent.section_id) : undefined} />
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
  maps, section, onSelectBlock, onSelectSection,
}: {
  maps: DerivedMaps
  section: IRSection
  onSelectBlock: (id: string) => void
  onSelectSection: (id: string) => void
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
          <ParentCard parent={parent} childCount={childList.length} />
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

// ── ③ 文档总览 ──────────────────────────────────────────────

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
        一份文档要经过这条隐藏流水线，才能被检索与回答。点左侧文档树或中间版面框，逐块透视。
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
