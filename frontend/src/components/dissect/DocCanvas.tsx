// 解析透视 · 文档画布（PDF 页渲染 + 版面块 bbox 叠加 + 父块并集大框）
// 这是「坐标锚定」难点的可视化主场：每个版面元素按类型层位着色精确框出，
// 父切片以虚线大框聚合，点击任一框 → 选中该块联动右栏与文档树。

import { useEffect, useLayoutEffect, useRef, useState } from "react"
import { Document, Page, pdfjs } from "react-pdf"
import { motion } from "motion/react"
import {
  Boxes, ChevronLeft, ChevronRight, Layers, Loader2, Palette,
} from "lucide-react"
import type { IRBlock } from "@/api/types"
import { cn } from "@/lib/utils"
import { normBox, typeMeta, type Box, type ParentBoxEntry } from "./helpers"

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString()

export interface CanvasLayers { blocks: boolean; parents: boolean; color: boolean }

export function DocCanvas({
  pdfUrl, pageIdx, pageCount, blocks, parentBoxes,
  selectedBlockId, hoveredBlockId, activeSectionId, selectedParentId,
  layers, onLayers, onSelectBlock, onSelectParent, onHoverBlock, onPageChange,
}: {
  pdfUrl: string
  pageIdx: number               // 0-based
  pageCount: number
  blocks: IRBlock[]             // 当前页的块
  parentBoxes: Map<string, ParentBoxEntry[]>  // 父块大框（parent 粒度，跨多 section 聚合）
  selectedBlockId: string | null
  hoveredBlockId: string | null
  activeSectionId: string | null
  selectedParentId: string | null
  layers: CanvasLayers
  onLayers: (l: CanvasLayers) => void
  onSelectBlock: (id: string) => void
  onSelectParent: (id: string) => void
  onHoverBlock: (id: string | null) => void
  onPageChange: (pageIdx: number) => void
}) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const [pdfWidth, setPdfWidth] = useState(680)
  const [rendered, setRendered] = useState(false)

  // 容器宽度自适应 PDF 渲染宽度
  useLayoutEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const ro = new ResizeObserver(() => {
      const w = el.clientWidth - 32
      setPdfWidth(Math.max(320, Math.min(900, w)))
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  useEffect(() => { setRendered(false) }, [pageIdx, pdfUrl])

  // 当前页的父块并集大框（selected 父块突出，其余作结构带）
  const pageParentBoxes: Array<{ pid: string; box: Box; selected: boolean }> = []
  if (layers.parents) {
    for (const [pid, entries] of parentBoxes) {
      for (const e of entries) {
        if (e.page_idx !== pageIdx) continue
        pageParentBoxes.push({ pid, box: e.box, selected: pid === selectedParentId })
      }
    }
  }

  return (
    <div className="flex h-full flex-col">
      {/* 工具条：翻页 + 图层开关 */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-3.5 py-2.5">
        <div className="flex items-center gap-1">
          <NavBtn onClick={() => onPageChange(pageIdx - 1)} disabled={pageIdx <= 0}>
            <ChevronLeft className="h-4 w-4" />
          </NavBtn>
          <span className="min-w-[64px] text-center font-mono text-xs tabular-nums text-ink-soft">
            p.{pageIdx + 1} / {pageCount}
          </span>
          <NavBtn onClick={() => onPageChange(pageIdx + 1)} disabled={pageIdx >= pageCount - 1}>
            <ChevronRight className="h-4 w-4" />
          </NavBtn>
        </div>
        <div className="ml-auto flex items-center gap-1.5">
          <LayerToggle active={layers.blocks} onClick={() => onLayers({ ...layers, blocks: !layers.blocks })} icon={Boxes}>块框</LayerToggle>
          <LayerToggle active={layers.parents} onClick={() => onLayers({ ...layers, parents: !layers.parents })} icon={Layers}>父块</LayerToggle>
          <LayerToggle active={layers.color} onClick={() => onLayers({ ...layers, color: !layers.color })} icon={Palette}>类型色</LayerToggle>
        </div>
      </div>

      {/* 画布 */}
      <div ref={wrapRef} className="min-h-0 flex-1 overflow-auto bg-surface-2/50 p-4">
        <div className="mx-auto w-fit">
          <div className="relative shadow-pop">
            <Document
              file={pdfUrl}
              loading={<PdfPlaceholder text="PDF 加载中…" spin />}
              error={<PdfPlaceholder text="origin.pdf 加载失败（该文档可能无 PDF 版面）" />}
            >
              <Page
                pageNumber={pageIdx + 1}
                width={pdfWidth}
                renderAnnotationLayer={false}
                renderTextLayer={false}
                onRenderSuccess={() => setRendered(true)}
                loading={<PdfPlaceholder text="渲染中…" spin />}
              />
            </Document>

            {/* 父块并集大框（虚线，在块框之下；点击空白区→选父块）。
                块框 z-index 更高且在其上，故点块仍选块、点父块空白区才选父块。 */}
            {rendered && pageParentBoxes.map(({ pid, box, selected }, i) => (
              <button
                key={`p-${pid}-${i}`}
                type="button"
                onClick={() => onSelectParent(pid)}
                title="父块（点击查看父块信息：含哪些块/子块/资产/索引）"
                className="group absolute cursor-pointer rounded-[3px] focus:outline-none"
                style={{
                  left: `${box.left}%`, top: `${box.top}%`,
                  width: `${box.width}%`, height: `${box.height}%`,
                  border: `1.5px dashed ${selected ? "var(--c-accent)" : "var(--c-border-strong)"}`,
                  background: selected ? "color-mix(in srgb, var(--c-accent) 7%, transparent)" : "transparent",
                  zIndex: selected ? 5 : 1,
                }}
              >
                {/* hover 时整框透出淡 accent 提示可点 */}
                <span
                  className={cn(
                    "pointer-events-none absolute inset-0 rounded-[2px] transition-opacity",
                    selected ? "opacity-0" : "opacity-0 group-hover:opacity-100",
                  )}
                  style={{ background: "color-mix(in srgb, var(--c-accent) 6%, transparent)" }}
                />
                {/* 父块标签 */}
                <span
                  className={cn(
                    "pointer-events-none absolute -top-[15px] left-0 whitespace-nowrap rounded px-1 py-px font-mono text-[9px] font-semibold leading-none text-white transition-opacity",
                    selected ? "opacity-100" : "opacity-0 group-hover:opacity-100",
                  )}
                  style={{ background: "var(--c-accent)" }}
                >
                  父块
                </span>
              </button>
            ))}

            {/* 块 bbox 框 */}
            {rendered && layers.blocks && blocks.map((b) => {
              const box = normBox(b.bbox_norm1000)
              if (!box) return null
              const meta = typeMeta(b.type)
              const color = layers.color ? meta.color : "var(--c-accent)"
              const isSel = b.block_id === selectedBlockId
              const isHover = b.block_id === hoveredBlockId
              const inActive = !isSel && b.section_id === activeSectionId
              return (
                <motion.button
                  key={b.block_id}
                  initial={false}
                  onClick={() => onSelectBlock(b.block_id)}
                  onMouseEnter={() => onHoverBlock(b.block_id)}
                  onMouseLeave={() => onHoverBlock(null)}
                  className="absolute block rounded-[3px] text-left focus:outline-none"
                  style={{
                    left: `${box.left}%`, top: `${box.top}%`,
                    width: `${box.width}%`, height: `${box.height}%`,
                    border: `${isSel ? 2.5 : isHover ? 2 : 1.25}px solid ${color}`,
                    background: isSel
                      ? `color-mix(in srgb, ${color} 22%, transparent)`
                      : isHover
                        ? `color-mix(in srgb, ${color} 14%, transparent)`
                        : inActive
                          ? `color-mix(in srgb, ${color} 9%, transparent)`
                          : `color-mix(in srgb, ${color} 5%, transparent)`,
                    boxShadow: isSel ? `0 0 0 3px color-mix(in srgb, ${color} 22%, transparent)` : "none",
                    zIndex: isSel ? 20 : isHover ? 15 : 10,
                  }}
                  title={`${meta.label} · ${b.text.slice(0, 40)}`}
                >
                  {(isSel || isHover) && (
                    <span
                      className="absolute -top-[18px] left-0 whitespace-nowrap rounded px-1 py-px font-mono text-[9px] font-semibold leading-none text-white"
                      style={{ background: color }}
                    >
                      {meta.label}
                    </span>
                  )}
                </motion.button>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}

function NavBtn({ children, onClick, disabled }: {
  children: React.ReactNode; onClick: () => void; disabled?: boolean
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="flex h-7 w-7 items-center justify-center rounded-lg border border-border bg-surface text-ink-soft transition-colors hover:text-ink disabled:opacity-35"
    >
      {children}
    </button>
  )
}

function LayerToggle({ active, onClick, icon: Icon, children }: {
  active: boolean; onClick: () => void
  icon: React.ComponentType<{ className?: string }>; children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-[11px] font-medium transition-colors",
        active
          ? "border-accent/40 bg-accent-soft text-accent-strong"
          : "border-border bg-surface text-ink-faint hover:text-ink-soft",
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {children}
    </button>
  )
}

function PdfPlaceholder({ text, spin }: { text: string; spin?: boolean }) {
  return (
    <div className="flex min-h-[320px] min-w-[280px] items-center justify-center gap-2 rounded-lg bg-surface p-8 text-sm text-ink-soft">
      {spin && <Loader2 className="h-4 w-4 animate-spin text-accent" />}
      {text}
    </div>
  )
}
